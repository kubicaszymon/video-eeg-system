/*
 * ==========================================================================
 *  lslstreamreader.cpp — LSL Data Acquisition Implementation
 * ==========================================================================
 *  See lslstreamreader.h for architecture overview and data flow.
 * ==========================================================================
 */

#include "lslstreamreader.h"
#include <QDebug>

LSLStreamReader::LSLStreamReader(QObject* parent)
    : QObject(parent)
{}

LSLStreamReader::~LSLStreamReader()
{
    /* Safety net: if the worker thread is being destroyed while still running,
     * ensure the inlet is cleanly closed to avoid dangling LSL connections. */
    onStopReading();
}

void LSLStreamReader::onStartReading()
{
    /* Guard against duplicate invocations — can happen if the user clicks
     * "connect" rapidly or if a delayed QTimer::singleShot fires twice. */
    if (m_isRunning)
    {
        qDebug() << "LSL reader already running";
        return;
    }

    try {
        /*
         * resolve_stream() performs a network multicast/broadcast to discover
         * any LSL outlet publishing type="EEG". The 5-second timeout allows
         * for Svarog Streamer startup latency. Only the first matching stream
         * is used — multi-amplifier setups are not currently supported.
         */
        qDebug() << "Resolving LSL stream";
        std::vector<lsl::stream_info> results = lsl::resolve_stream("type", "EEG", 1, 5.0);

        if (results.empty())
        {
            emit errorOccurred("No EEG stream found");
            return;
        }

        lsl::stream_info info = results[0];
        double samplingRate = info.nominal_srate();
        qDebug() << "LSL stream sampling rate:" << samplingRate << "Hz";

        m_inlet = new lsl::stream_inlet(info);
        qDebug() << "Connected to LSL stream";

        /* Notify downstream components in dependency order:
         * 1. inletReady    → EegSyncManager needs the inlet for time_correction()
         * 2. samplingRate  → EegBackend/EegDataModel configure buffer sizes
         * 3. connected     → UI updates connection status indicators */
        emit inletReady(m_inlet);
        emit samplingRateDetected(samplingRate);
        emit streamConnected();

        m_isRunning = true;
        readLoop();
    }
    catch (const std::exception& e)
    {
        emit errorOccurred(QString("LSL error: %1").arg(e.what()));
    }
}

void LSLStreamReader::onStopReading()
{
    /* Atomic write breaks the readLoop() while-condition. The loop will
     * exit within one poll cycle (~20ms). */
    m_isRunning = false;

    if (m_inlet)
    {
        /* Signal nullptr first so EegSyncManager releases its reference
         * before the inlet object is deleted. */
        emit inletReady(nullptr);
        delete m_inlet;
        m_inlet = nullptr;
        emit streamDisconnected();
    }
}

void LSLStreamReader::readLoop()
{
    std::vector<std::vector<float>> chunk;
    std::vector<double> timestamps;

    while (m_isRunning)
    {
        try
        {
            /*
             * pull_chunk() retrieves all samples buffered since the last call.
             * Returns immediately if no data is available (non-blocking).
             * Typical chunk size: ~5-10 samples at 256 Hz with 20ms poll interval.
             */
            m_inlet->pull_chunk(chunk, timestamps);
            if (!chunk.empty())
            {
                emit dataReceived(chunk, timestamps);
                chunk.clear();
                timestamps.clear();
            }
        }
        catch (const std::exception& e)
        {
            emit errorOccurred(QString("Read error: %1").arg(e.what()));
        }

        /* 20ms sleep = ~50 Hz poll rate. This prevents CPU spinning while
         * remaining responsive enough for real-time EEG display. At 256 Hz
         * sampling, each poll yields ~5 samples on average. */
        QThread::sleep(std::chrono::milliseconds(20));
    }
}
