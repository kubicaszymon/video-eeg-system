/*
 * ==========================================================================
 *  EegBackend.cpp — Central EEG Data Router Implementation
 * ==========================================================================
 *  See EegBackend.h for architecture overview, data routing diagram,
 *  and initialization sequence.
 * ==========================================================================
 */

#include "EegBackend.h"
#include "recordingmanager.h"
#include <QDebug>
#include <QtMath>
#include <lsl_cpp.h>

EegBackend::EegBackend(QObject *parent)
    : QObject{parent}
    , m_amplifierManager{AmplifierManager::instance()}
    , m_markerManager{new MarkerManager(this)}
    , m_scaler{new EegDisplayScaler(this)}
{
    qInfo() << "[EegBackend] Created:" << this;

    /* All connections use Qt::QueuedConnection because AmplifierManager
     * relays signals from the LSL worker thread. This ensures all slot
     * execution happens safely on the main thread. */
    connect(m_amplifierManager, &AmplifierManager::dataReceived,
            this, &EegBackend::onDataReceived, Qt::QueuedConnection);
    connect(m_amplifierManager, &AmplifierManager::samplingRateDetected,
            this, &EegBackend::onSamplingRateDetected, Qt::QueuedConnection);
    connect(m_amplifierManager, &AmplifierManager::streamConnected,
            this, &EegBackend::onStreamConnected, Qt::QueuedConnection);
    connect(m_amplifierManager, &AmplifierManager::streamDisconnected,
            this, &EegBackend::onStreamDisconnected, Qt::QueuedConnection);
}

EegBackend::~EegBackend()
{
    qDebug() << "[EegBackend] Destructor called";
}

// ============================================================================
// Initialization
// ============================================================================

void EegBackend::registerDataModel(EegDataModel *dataModel)
{
    /* The EegDataModel is instantiated in the QML layer (EegWindow.qml) and
     * passed here via Q_INVOKABLE so the C++ backend can write data to it.
     * We store a raw pointer (not owned) — the QML engine manages the
     * model's lifetime as part of the QML component tree. */
    if (dataModel)
    {
        m_dataModel = dataModel;
        qInfo() << "[EegBackend] Data model registered:" << m_dataModel;
    }
}

void EegBackend::startStream()
{
    /* Immediately switch to "connecting" state so the UI can show a spinner.
     * The actual connection happens asynchronously — onStreamConnected()
     * will flip the state to "connected" once LSL resolves the stream. */
    m_isConnecting = true;
    m_isConnected = false;
    emit isConnectingChanged();
    emit isConnectedChanged();

    m_amplifierManager->startStream(m_amplifierId);
}

void EegBackend::stopStream()
{
    /* Delegates the full shutdown sequence to AmplifierManager (LSL reader
     * stop → thread teardown → Svarog process kill). Then resets our
     * connection state flags so the UI returns to the disconnected state. */
    m_amplifierManager->stopStream();

    m_isConnecting = false;
    m_isConnected = false;
    emit isConnectingChanged();
    emit isConnectedChanged();
}

// ============================================================================
// Connection State Handlers
// ============================================================================

void EegBackend::onStreamConnected()
{
    qInfo() << "[EegBackend] Stream connected";
    m_isConnecting = false;
    m_isConnected = true;
    emit isConnectingChanged();
    emit isConnectedChanged();
}

void EegBackend::onStreamDisconnected()
{
    qInfo() << "[EegBackend] Stream disconnected";
    m_isConnecting = false;
    m_isConnected = false;
    emit isConnectingChanged();
    emit isConnectedChanged();
}

void EegBackend::onSamplingRateDetected(double samplingRate)
{
    qDebug() << "[EegBackend] Sampling rate detected:" << samplingRate << "Hz";

    if (!qFuzzyCompare(m_samplingRate, samplingRate))
    {
        m_samplingRate = samplingRate;
        emit samplingRateChanged();

        /* Configure downstream buffer sizes now that we know the actual
         * sampling rate. The EegDataModel needs this to calculate
         * m_maxSamples = samplingRate × timeWindowSeconds. */
        if (m_dataModel)
        {
            m_dataModel->setSamplingRate(samplingRate);
            m_dataModel->setTimeWindowSeconds(m_timeWindowSeconds);
        }

        EegSyncManager::instance()->setSamplingRate(samplingRate);
    }
}

// ============================================================================
// Data Processing — THE HOT PATH
// ============================================================================

void EegBackend::onDataReceived(const std::vector<std::vector<float>>& chunk,
                                 const std::vector<double>& timestamps)
{
    if (chunk.empty() || chunk[0].empty() || m_channels.isEmpty() || !m_dataModel)
    {
        return;
    }

    updateChannelIndexCache();

    /* Route 1: DISPLAY — scale μV→pixels and write to circular buffer.
     * This is the only route that transforms the data; routes 2 and 3
     * receive the raw μV values with LSL timestamps for fidelity. */
    QVector<QVector<double>> scaledData = m_scaler->transformChunk(
        chunk, m_channelIndexCache, m_spacing);

    int prevWritePos = m_dataModel->writePosition();
    m_dataModel->updateAllData(scaledData);
    updateMarkersAfterWrite(prevWritePos, m_dataModel->writePosition());

    /* Route 2: SYNC BUFFER — raw data with timestamps for EEG-video alignment.
     * EegSyncManager stores these in a ring buffer that VideoBackend queries
     * to find the EEG data corresponding to each video frame's timestamp. */
    if (!timestamps.empty())
    {
        EegSyncManager::instance()->addEegSamples(chunk, timestamps, m_channelIndexCache);
    }

    /* Route 3: RECORDING — raw data forwarded to RecordingManager.
     * RecordingManager checks internally whether recording is active;
     * if not, this is a no-op. If active, data is batched and flushed
     * to CSV on the RecordingWorker thread. */
    RecordingManager::instance()->writeEegData(chunk, timestamps, m_channelIndexCache);
}

void EegBackend::updateChannelIndexCache()
{
    /* Lazy rebuild: only re-converts when channel count changes.
     * Avoids per-chunk QVariant→int conversion overhead on the hot path. */
    const int numChannels = m_channels.size();

    if (m_channelIndexCache.size() != numChannels)
    {
        m_channelIndexCache.resize(numChannels);
        for (int i = 0; i < numChannels; ++i)
        {
            m_channelIndexCache[i] = m_channels[i].toInt();
        }
    }
}

void EegBackend::updateMarkersAfterWrite(int prevWritePos, int newWritePos)
{
    if (!m_markerManager || m_samplingRate <= 0 || !m_dataModel)
        return;

    /* Convert buffer positions to X-axis time coordinates, then tell
     * MarkerManager to remove any markers in the overwritten range. */
    double startX = static_cast<double>((prevWritePos + 1) % m_dataModel->maxSamples()) / m_samplingRate;
    double endX = static_cast<double>(newWritePos) / m_samplingRate;

    m_markerManager->removeMarkersInRange(startX, endX, m_timeWindowSeconds);
}

// ============================================================================
// Markers
// ============================================================================

void EegBackend::addMarker(const QString& type)
{
    if (!m_markerManager || !m_dataModel || m_samplingRate <= 0)
    {
        qWarning() << "[EegBackend] Cannot add marker - not ready";
        return;
    }

    /* Place the marker at the current write cursor position.
     * Convert buffer index to time-in-seconds for the X coordinate. */
    int writePos = m_dataModel->writePosition();
    double xPosition = static_cast<double>(writePos) / m_samplingRate;

    qInfo() << "[EegBackend] Adding marker" << type << "at X:" << xPosition;
    m_markerManager->addMarkerAtPosition(type, xPosition, xPosition);

    /* Simultaneously record the marker with an LSL timestamp for export.
     * The LSL timestamp provides absolute time correlation with EEG data. */
    QString label = MarkerManager::getLabelForType(type);
    RecordingManager::instance()->writeMarker(type, label, lsl::local_clock());
}

// ============================================================================
// Test Data Generation
// ============================================================================

void EegBackend::generateTestData()
{
    if (!m_dataModel)
        return;

    const int numChannels = m_channels.size();
    const int numSamples = 500;

    QVector<QVector<double>> testData(numChannels);

    for (int ch = 0; ch < numChannels; ++ch)
    {
        testData[ch].reserve(numSamples);
        double offset = EegDisplayScaler::calculateChannelOffset(ch, numChannels, m_spacing);

        for (int i = 0; i < numSamples; ++i)
        {
            double time = i * 0.1;
            double value = qSin(time * (1.0 + ch * 0.3)) * (m_spacing * 0.3);
            testData[ch].append(offset - value);
        }
    }

    m_dataModel->updateAllData(testData);
}

// ============================================================================
// Channel Configuration
// ============================================================================

QVariantList EegBackend::channels() const
{
    return m_channels;
}

void EegBackend::setChannels(const QVariantList &newChannels)
{
    if (m_channels == newChannels)
        return;

    m_channels = newChannels;

    /* Clear the cache so updateChannelIndexCache() will rebuild it from
     * the new QVariantList on the next onDataReceived() call. */
    m_channelIndexCache.clear();
    emit channelsChanged();
}

QStringList EegBackend::channelNames() const
{
    /* Resolves numeric channel indices to human-readable names (e.g. "Fp1")
     * by looking up the amplifier's available_channels list. Falls back to
     * "Ch N" if the amplifier metadata is unavailable. */
    QStringList names;

    Amplifier* amp = m_amplifierManager->getAmplifierById(m_amplifierId);

    for (const auto& channelVar : m_channels)
    {
        int channelIndex = channelVar.toInt();

        if (amp && channelIndex >= 0 && channelIndex < amp->available_channels.size())
        {
            names.append(amp->available_channels[channelIndex]);
        }
        else
        {
            names.append(QString("Ch %1").arg(channelIndex));
        }
    }

    return names;
}

// ============================================================================
// Amplifier Configuration
// ============================================================================

int EegBackend::amplifierIdx() const
{
    return m_amplifierIdx;
}

void EegBackend::setAmplifierIdx(int newAmplifierIdx)
{
    if (m_amplifierIdx == newAmplifierIdx)
        return;

    m_amplifierIdx = newAmplifierIdx;
    emit amplifierIdxChanged();
}

QString EegBackend::amplifierId() const
{
    return m_amplifierId;
}

void EegBackend::setAmplifierId(const QString &newAmplifierId)
{
    if (m_amplifierId == newAmplifierId)
        return;

    m_amplifierId = newAmplifierId;
    emit amplifierIdChanged();
}

// ============================================================================
// Display Configuration
// ============================================================================

double EegBackend::spacing() const
{
    return m_spacing;
}

void EegBackend::setSpacing(double newSpacing)
{
    /* Spacing changes take effect immediately on the next data chunk —
     * EegDisplayScaler::transformChunk() uses the spacing parameter to
     * calculate channel baseline offsets. No buffer reallocation needed. */
    if (qFuzzyCompare(m_spacing, newSpacing))
        return;

    m_spacing = newSpacing;
    emit spacingChanged();
}

double EegBackend::timeWindowSeconds() const
{
    return m_timeWindowSeconds;
}

void EegBackend::setTimeWindowSeconds(double newTimeWindowSeconds)
{
    /* Time window change is a heavy operation: it triggers buffer reallocation
     * in EegDataModel (discards all visible data) and clears all markers
     * (their X positions are relative to the old window size). */
    if (qFuzzyCompare(m_timeWindowSeconds, newTimeWindowSeconds))
        return;

    m_timeWindowSeconds = newTimeWindowSeconds;
    emit timeWindowSecondsChanged();

    /* Propagate to EegDataModel which will recalculate m_maxSamples
     * and reinitialize its buffer. */
    if (m_dataModel)
    {
        m_dataModel->setTimeWindowSeconds(m_timeWindowSeconds);
    }

    /* Markers placed at old time-window coordinates are now meaningless
     * (e.g. a marker at X=8.5 in a 10s window has no meaning in a 5s window).
     * Clear them to avoid visual artifacts. */
    if (m_markerManager)
    {
        m_markerManager->clearMarkers();
    }
}

double EegBackend::samplingRate() const
{
    return m_samplingRate;
}
