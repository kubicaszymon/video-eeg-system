/*
 * ==========================================================================
 *  amplifiermanager.cpp — Amplifier Orchestration Implementation
 * ==========================================================================
 *  See amplifiermanager.h for architecture overview, data flow, and
 *  startup/shutdown sequences.
 * ==========================================================================
 */

#include <QDebug>
#include <QRegularExpression>

#include "amplifiermodel.h"
#include "amplifiermanager.h"
#include "eegsyncmanager.h"
#include <lsl_cpp.h>
#include <qtimer.h>

AmplifierManager::AmplifierManager(QObject* parent)
    : QObject(parent)
{
}

AmplifierManager::~AmplifierManager()
{
    stopStream();
}

AmplifierManager *AmplifierManager::instance()
{
    static AmplifierManager instance;
    return &instance;
}

// ============================================================================
// Device Discovery
// ============================================================================

QList<Amplifier> AmplifierManager::refreshAmplifiersList()
{
    /* Blocking scan: spawns svarog_streamer with the -l (list) flag and waits
     * for it to finish. The process scans USB for connected EEG amplifiers and
     * prints their metadata to stdout. Typical execution time: 1-2 seconds. */
    qInfo() << "Refreshing amplifiers list";
    QList<Amplifier> rv{};
    QProcess process;
    process.setProgram(m_svarogPath);
    process.setArguments({"-l"});
    process.start();

    if (process.waitForFinished(PROCESS_TIMEOUT_MS))
    {
        QByteArray output = process.readAllStandardOutput();
        rv = parseRawOutputToAmplifiers(output);
    }
    else
    {
        qDebug() << "Failed to retrieve amplifiers list";
    }

    /* Cache result so getAmplifierById() can look up metadata later. */
    m_amplifiers = rv;
    return rv;
}

void AmplifierManager::refreshAmplifiersListAsync()
{
    /* Non-blocking scan: same as refreshAmplifiersList() but uses QProcess
     * signal/slot completion instead of waitForFinished(). This keeps the
     * main thread responsive while the USB scan runs (important because
     * svarog_streamer can take several seconds to enumerate devices). */
    qInfo() << "Starting async amplifier scan...";

    /* Guard against overlapping scans — only one scan at a time. */
    if (m_scanProcess && m_scanProcess->state() == QProcess::Running)
    {
        qDebug() << "Scan already in progress";
        return;
    }

    /* Clean up any previous process object before creating a new one. */
    if (m_scanProcess)
    {
        m_scanProcess->deleteLater();
        m_scanProcess = nullptr;
    }

    m_scanProcess = new QProcess(this);
    m_scanProcess->setProgram(m_svarogPath);
    m_scanProcess->setArguments({"-l"});

    connect(m_scanProcess, &QProcess::finished, this, &AmplifierManager::onScanProcessFinished);

    m_scanProcess->start();
}

void AmplifierManager::onScanProcessFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    /* Callback from the async scan process. Parses the stdout output into
     * Amplifier structs and notifies the UI via amplifiersListRefreshed(). */
    Q_UNUSED(exitCode)
    Q_UNUSED(exitStatus)

    QList<Amplifier> rv{};

    if (m_scanProcess)
    {
        QByteArray output = m_scanProcess->readAllStandardOutput();
        rv = parseRawOutputToAmplifiers(output);
        m_amplifiers = rv;

        m_scanProcess->deleteLater();
        m_scanProcess = nullptr;
    }

    emit amplifiersListRefreshed(rv);
}

Amplifier* AmplifierManager::getAmplifierById(const QString& id)
{
    /* Linear search through cached amplifiers. The list is typically 1-3
     * entries, so a linear scan is faster than a hash map lookup. */
    auto it = std::find_if(m_amplifiers.begin(), m_amplifiers.end(), [&](Amplifier& amp) {
        return amp.id == id;
    });
    return it != m_amplifiers.end() ? &*it : nullptr;
}

// ============================================================================
// Stream Lifecycle
// ============================================================================

void AmplifierManager::startStream(const QString& amplifierId)
{
    if (m_streamProcess && m_streamProcess->state() == QProcess::Running)
    {
        qDebug() << "Stopping existing stream";
        stopStream();
    }

    /* Step 1: Launch Svarog Streamer in acquisition mode.
     * The "-a" flag tells it to start streaming from the specified amplifier
     * and publish the data as an LSL outlet of type "EEG". */
    m_streamProcess = new QProcess(this);
    m_streamProcess->setProgram(m_svarogPath);
    m_streamProcess->setArguments({"-a", amplifierId});
    m_streamProcess->start();

    if (!m_streamProcess->waitForStarted(PROCESS_TIMEOUT_MS))
    {
        qDebug() << "Failed to start stream process";
        delete m_streamProcess;
        m_streamProcess = nullptr;
        return;
    }

    /* Step 2: Create the LSL reader infrastructure (only once).
     * The reader is moved to a dedicated thread so its blocking readLoop()
     * does not freeze the main thread / UI. */
    if (!m_lslThread)
    {
        m_lslThread = new QThread(this);
        m_lslReader = std::make_unique<LSLStreamReader>();
        m_lslReader->moveToThread(m_lslThread);

        /* Wire signal/slot connections across threads:
         * - dataReceived:    LSL data → this manager → downstream consumers
         * - inletReady:      passes the raw lsl::stream_inlet* to EegSyncManager
         *                    so it can call time_correction() for clock alignment
         * - samplingRate:    propagated to EegBackend/EegDataModel for buffer sizing
         * - connected/disc:  UI state updates
         * - start/stopLsl:   control signals FROM this manager TO the reader */
        connect(m_lslReader.get(), &LSLStreamReader::dataReceived, this, &AmplifierManager::onProcessData);
        connect(m_lslReader.get(), &LSLStreamReader::inletReady, this, [](lsl::stream_inlet* inlet) {
            EegSyncManager::instance()->setLslInlet(inlet);
        });
        connect(m_lslReader.get(), &LSLStreamReader::samplingRateDetected, this, &AmplifierManager::onSamplingRateDetected);
        connect(m_lslReader.get(), &LSLStreamReader::streamConnected, this, &AmplifierManager::streamConnected);
        connect(m_lslReader.get(), &LSLStreamReader::streamDisconnected, this, &AmplifierManager::streamDisconnected);
        connect(this, &AmplifierManager::startLslReading, m_lslReader.get(), &LSLStreamReader::onStartReading);
        connect(this, &AmplifierManager::stopLslReading, m_lslReader.get(), &LSLStreamReader::onStopReading);

        m_lslThread->start();
    }

    /* Step 3: Delayed start — give Svarog Streamer time to initialize
     * its LSL outlet before the reader attempts to resolve it. */
    QTimer::singleShot(STREAM_STARTUP_DELAY_MS, this, [this]() {
        emit startLslReading();
    });
}

void AmplifierManager::stopStream()
{
    qDebug() << "Stopping stream";

    /* Phase 1: Stop the LSL reader loop.
     * The 100ms sleep gives the readLoop() time to see m_isRunning==false
     * and exit before we tear down the thread. */
    if (m_lslReader)
    {
        emit stopLslReading();
        QThread::msleep(100);
    }

    /* Phase 2: Shut down the worker thread.
     * quit() asks the event loop to stop; wait(3s) gives it time.
     * terminate() is the last resort if the thread is stuck in a
     * blocking LSL call. */
    if (m_lslThread)
    {
        if (m_lslThread->isRunning())
        {
            m_lslThread->quit();
            if (!m_lslThread->wait(3000))
            {
                m_lslThread->terminate();
                m_lslThread->wait();
            }
        }

        m_lslThread->deleteLater();
        m_lslThread = nullptr;
    }

    m_lslReader.reset();

    /* Phase 3: Shut down the Svarog Streamer process.
     * terminate() sends a graceful close signal; kill() forces it. */
    if (m_streamProcess)
    {
        if (m_streamProcess->state() == QProcess::Running)
        {
            m_streamProcess->terminate();
            if (!m_streamProcess->waitForFinished(3000))
            {
                m_streamProcess->kill();
                m_streamProcess->waitForFinished();
            }
        }

        m_streamProcess->deleteLater();
        m_streamProcess = nullptr;
    }
}

// ============================================================================
// Configuration
// ============================================================================

QString AmplifierManager::svarogPath() const
{
    return m_svarogPath;
}

void AmplifierManager::setSvarogPath(const QString& newSvarogPath)
{
    m_svarogPath = newSvarogPath;
}

// ============================================================================
// Signal Relay (worker thread → main thread)
// ============================================================================

void AmplifierManager::onProcessData(const std::vector<std::vector<float>>& chunk,
                                      const std::vector<double>& timestamps)
{
    /* Simple relay: re-emit the data signal so that main-thread consumers
     * (EegBackend, etc.) can connect to AmplifierManager rather than needing
     * a direct reference to the LSLStreamReader on the worker thread. */
    emit dataReceived(chunk, timestamps);
}

void AmplifierManager::onSamplingRateDetected(double samplingRate)
{
    /* Relay the sampling rate from LSLStreamReader to all consumers.
     * This value comes from lsl::stream_info::nominal_srate() and is
     * critical for buffer sizing (EegDataModel) and time calculations. */
    qDebug() << "AmplifierManager: Sampling rate detected:" << samplingRate << "Hz";
    emit AmplifierManager::samplingRateDetected(samplingRate);
}

// ============================================================================
// Svarog Output Parser
// ============================================================================

QList<Amplifier> AmplifierManager::parseRawOutputToAmplifiers(const QByteArray& output)
{
    /*
     * Parses the structured text output of `svarog_streamer -l`.
     * The output format is a simple indented-text protocol:
     *
     *   * Perun32
     *     id: "usb:002/005"
     *     available channels:
     *       Fp1 Fp2 C3 C4 O1 O2 ...
     *     available sampling rates:
     *       256 512 1024
     *
     * The parser uses a state machine with three states:
     *   inAmplifier     — inside an amplifier block (after "* ")
     *   inChannels      — reading channel names (after "available channels:")
     *   inSamplingRates — reading rates (after "available sampling rates:")
     */
    QList<Amplifier> amplifiers;
    QString text = QString::fromUtf8(output);
    QStringList lines = text.split('\n', Qt::SkipEmptyParts);

    Amplifier currentAmp;
    bool inAmplifier = false;
    bool inChannels = false;
    bool inSamplingRates = false;

    for (const QString& line : std::as_const(lines))
    {
        QString trimmed = line.trimmed();

        if (trimmed.startsWith("* "))
        {
            if (inAmplifier && !currentAmp.name.isEmpty())
            {
                amplifiers.append(currentAmp);
            }

            currentAmp = Amplifier();
            currentAmp.name = trimmed.mid(2).trimmed();
            inAmplifier = true;
            inChannels = false;
            inSamplingRates = false;
        }
        else if (trimmed.startsWith("id:"))
        {
            static QRegularExpression idRegex(R"(id:\s*"([^"]+)\")");
            QRegularExpressionMatch match = idRegex.match(trimmed);
            if (match.hasMatch())
            {
                currentAmp.id = match.captured(1);
            }
        }
        else if (trimmed.contains("available channels:"))
        {
            inChannels = true;
            inSamplingRates = false;
        }
        else if (trimmed.contains("available sampling rates:"))
        {
            inChannels = false;
            inSamplingRates = true;
        }
        else if (inChannels && !trimmed.isEmpty() && !trimmed.contains("available"))
        {
            static QRegularExpression re("\\s+");
            QStringList channels = trimmed.split(re, Qt::SkipEmptyParts);
            currentAmp.available_channels.append(channels);
        }
        else if (inSamplingRates && !trimmed.isEmpty() && !trimmed.contains("available"))
        {
            static QRegularExpression re("\\s+");
            QStringList rates = trimmed.split(re, Qt::SkipEmptyParts);
            currentAmp.available_samplings.append(rates);
        }
    }

    if (inAmplifier && !currentAmp.name.isEmpty())
    {
        amplifiers.append(currentAmp);
    }

    return amplifiers;
}
