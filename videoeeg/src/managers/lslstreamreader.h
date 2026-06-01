/*
 * ==========================================================================
 *  lslstreamreader.h — Lab Streaming Layer (LSL) Data Acquisition Worker
 * ==========================================================================
 *
 *  PURPOSE:
 *    The lowest-level data acquisition component. Resolves an LSL network
 *    stream of type "EEG", opens an inlet, and continuously pulls data
 *    chunks in a blocking loop. This is the single entry point for ALL
 *    EEG data entering the application.
 *
 *  DESIGN PATTERN:
 *    Worker-Thread Object — instantiated on the main thread, then moved
 *    to a dedicated QThread owned by AmplifierManager. The readLoop()
 *    runs entirely on that worker thread. All communication with the main
 *    thread is via queued signal/slot connections.
 *
 *  THREADING MODEL:
 *    ┌─────────────────────────────────────────────────────────────┐
 *    │  LSL Worker Thread (managed by AmplifierManager)           │
 *    │                                                            │
 *    │  onStartReading()                                          │
 *    │    ├─ lsl::resolve_stream("type","EEG") — blocks up to 5s │
 *    │    ├─ new lsl::stream_inlet(info)                          │
 *    │    ├─ emit inletReady / samplingRateDetected / connected   │
 *    │    └─ readLoop()  ←── tight poll loop                      │
 *    │         ├─ inlet->pull_chunk()                             │
 *    │         ├─ emit dataReceived(chunk, timestamps)            │
 *    │         └─ sleep 20ms  ←── yield to prevent CPU spin       │
 *    └─────────────────────────────────────────────────────────────┘
 *              │ signals (Qt::QueuedConnection)
 *              ▼
 *    ┌──────────────────────────┐
 *    │  Main Thread             │
 *    │  AmplifierManager slots  │
 *    └──────────────────────────┘
 *
 *  DATA FORMAT:
 *    chunk      — std::vector<std::vector<float>>  [sample_index][channel_index]
 *                 Values in microvolts (μV), as delivered by Svarog Streamer.
 *    timestamps — std::vector<double>  [sample_index]
 *                 LSL timestamps (lsl::local_clock() domain, seconds since epoch).
 *
 *  LIFECYCLE:
 *    1. AmplifierManager creates LSLStreamReader, moves it to QThread.
 *    2. startLslReading signal → onStartReading() slot resolves stream.
 *    3. readLoop() runs until m_isRunning is set to false.
 *    4. stopLslReading signal → onStopReading() sets m_isRunning = false.
 *    5. AmplifierManager quits the thread and destroys the reader.
 *
 *  WHY 20ms SLEEP:
 *    pull_chunk() is non-blocking when no data is available. Without a
 *    sleep, the loop would spin at 100% CPU. 20ms gives ~50 Hz poll rate
 *    which is well above the typical EEG packet rate (~4 Hz at 256 Hz
 *    sampling with default LSL chunk sizes).
 *
 * ==========================================================================
 */

#ifndef LSLSTREAMREADER_H
#define LSLSTREAMREADER_H

#include <QObject>
#include <QThread>
#include <lsl_cpp.h>
#include <vector>
#include <atomic>

class LSLStreamReader : public QObject
{
    Q_OBJECT

public:
    explicit LSLStreamReader(QObject* parent = nullptr);

    /* Destructor calls onStopReading() to ensure clean shutdown
     * of the LSL inlet even if the caller forgets to stop explicitly. */
    ~LSLStreamReader();

signals:
    /* Emitted on every successful pull_chunk with non-empty data.
     * This is the primary data signal — the heart of the entire EEG pipeline.
     * chunk:      [sample][channel] raw EEG in μV
     * timestamps: [sample] LSL timestamps in seconds */
    void dataReceived(const std::vector<std::vector<float>>& chunk,
                      const std::vector<double>& timestamps);

    /* Emitted when the LSL inlet is created (non-null) or destroyed (nullptr).
     * EegSyncManager uses the inlet pointer to call time_correction()
     * for compensating clock drift between the amplifier and local machine. */
    void inletReady(lsl::stream_inlet* inlet);

    /* Emitted when an LSL operation throws — covers resolution failures,
     * read errors, and connection drops. */
    void errorOccurred(const QString& error);

    /* Emitted after successful stream resolution and inlet creation.
     * Used by AmplifierManager to relay connection state to UI. */
    void streamConnected();

    /* Emitted when the inlet is torn down (either explicit stop or error).
     * Triggers UI disconnected-state indicators. */
    void streamDisconnected();

    /* Emitted once after stream resolution, carries the nominal_srate()
     * from the LSL stream_info metadata. Downstream consumers
     * (EegDataModel, EegSyncManager) use this to size their buffers. */
    void samplingRateDetected(double samplingRate);

public slots:
    /* Slot triggered by AmplifierManager::startLslReading signal.
     * Resolves the LSL stream on the network, opens an inlet, and enters
     * the blocking readLoop(). This entire method runs on the worker thread. */
    void onStartReading();

    /* Slot triggered by AmplifierManager::stopLslReading signal.
     * Sets m_isRunning = false to break the readLoop(), then tears down
     * the inlet. Thread-safe: m_isRunning is std::atomic<bool>. */
    void onStopReading();

private:
    /* Blocking acquisition loop — runs on the worker thread until
     * m_isRunning is cleared by onStopReading(). Continuously calls
     * pull_chunk() with a 20ms sleep between iterations. */
    void readLoop();

    /* Atomic flag for cross-thread stop signaling. Set to true in
     * onStartReading(), cleared by onStopReading(). The readLoop()
     * checks this on every iteration. */
    std::atomic<bool> m_isRunning{false};

    /* Raw LSL inlet pointer — created in onStartReading(), destroyed
     * in onStopReading(). Null when no stream is active. */
    lsl::stream_inlet* m_inlet = nullptr;
};

#endif // LSLSTREAMREADER_H
