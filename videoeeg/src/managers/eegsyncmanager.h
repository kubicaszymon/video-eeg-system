/*
 * ==========================================================================
 *  eegsyncmanager.h — EEG-Video Synchronization Buffer
 * ==========================================================================
 *
 *  PURPOSE:
 *    Manages a rolling time-indexed buffer of raw EEG samples, enabling
 *    post-hoc lookup of the EEG data that was recorded at any given video
 *    frame timestamp. This is the bridge between the two real-time streams
 *    (EEG via LSL, video via camera) that run on independent clocks.
 *
 *  DESIGN PATTERNS:
 *    Singleton (QML_SINGLETON) — one shared instance across EegBackend
 *    (writer) and VideoBackend / VideoDisplayWindow (readers).
 *    Monitor — QMutex guards the buffer for safe concurrent access from
 *    the main thread (reads) and the hot-path EEG update (writes).
 *
 *  THE CLOCK DRIFT PROBLEM:
 *    The EEG amplifier's hardware clock and the PC's system clock run at
 *    slightly different rates and are offset from each other. Without
 *    correction, queries like "which EEG sample aligns with frame at t=T?"
 *    would accumulate error over time.
 *
 *    LSL's time_correction() solves this: it performs a network round-trip
 *    measurement and returns the offset to add to local_clock() values to
 *    convert them to the LSL-global time base. We refresh this correction
 *    every 10 seconds and apply it to every timestamp lookup, keeping
 *    synchronization accurate over 24-hour recordings.
 *
 *  DATA FLOW:
 *    [WRITE]  EegBackend::onDataReceived()
 *               → addEegSamples(chunk, timestamps, channelIndices)
 *                   • Stores raw μV values with LSL timestamps
 *                   • Enforces rolling max-size (30 s × sampling rate)
 *
 *    [READ]   VideoBackend / VideoDisplayWindow
 *               → getEEGForFrame(videoTimestamp)   — single-sample lookup
 *               → getEEGRangeForFrame(start, end)  — range query for a frame interval
 *
 *  INTERPOLATION MODES:
 *    Mode 0 (nearest neighbor) — O(log N) binary search, returns closest
 *      sample. Suitable for low-latency display annotation.
 *    Mode 1 (linear)           — Interpolates between the two samples
 *      bracketing the query timestamp. Provides smoother results for
 *      analysis where the inter-sample interval (~4 ms at 256 Hz) matters.
 *
 *  BUFFER SIZING:
 *    Default: 7680 samples = 30 s × 256 Hz. Recalculated when the actual
 *    sampling rate is confirmed by EegBackend::onSamplingRateDetected().
 *    The buffer always covers at least one full display window (~10 s)
 *    plus enough headroom for video-EEG alignment queries.
 *
 *  TIMESTAMP VALIDATION:
 *    getEEGForFrame() validates that the query timestamp falls within
 *    the buffer's time range [oldest, newest] before performing the
 *    search. If the timestamp is outside the buffer range, the result
 *    includes "outOfRange"=true and "rangeErrorMs" indicating how far
 *    the query timestamp is from the nearest buffer boundary. This
 *    prevents silent misalignment when the video and EEG streams have
 *    different start times or when one stream is lagging behind.
 *
 *  SESSION TRACKING:
 *    markSessionStart() records the LSL timestamp at which the recording
 *    session began. This enables session-relative time calculations and
 *    provides a reference point for aligning the EEG and video buffers
 *    when they start at different wall-clock times.
 *
 *  THREAD SAFETY:
 *    addEegSamples()         — called on the main thread from EegBackend
 *    getEEGForFrame()        — may be called from QML / UI thread
 *    All methods lock m_mutex before accessing m_buffer.
 *
 * ==========================================================================
 */

#ifndef EEGSYNCMANAGER_H
#define EEGSYNCMANAGER_H

#include <QObject>
#include <QMutex>
#include <QTimer>
#include <QVector>
#include <QVariantMap>
#include <QVariantList>
#include <QQmlEngine>
#include <QtQml/qqmlregistration.h>
#include <deque>
#include <vector>
#include <lsl_cpp.h>

/*
 * Timestamped EEG sample — the atomic unit stored in the sync buffer.
 * Intentionally lightweight: only the selected channels are stored (not
 * all hardware channels) to reduce memory footprint and copy cost.
 */
struct EegTimestampedSample
{
    double lslTimestamp = 0.0;
    std::vector<float> channels;

    EegTimestampedSample() = default;
    EegTimestampedSample(double ts, std::vector<float> vals)
        : lslTimestamp(ts), channels(std::move(vals)) {}

    bool isValid() const { return lslTimestamp > 0.0 && !channels.empty(); }
};

class EegSyncManager : public QObject
{
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

    // --- Buffer state (read-only from QML, for monitoring panel) ---
    Q_PROPERTY(int bufferSize READ bufferSize NOTIFY statsChanged FINAL)
    Q_PROPERTY(int maxBufferSize READ maxBufferSize WRITE setMaxBufferSize NOTIFY maxBufferSizeChanged FINAL)
    Q_PROPERTY(double oldestTimestamp READ oldestTimestamp NOTIFY statsChanged FINAL)
    Q_PROPERTY(double newestTimestamp READ newestTimestamp NOTIFY statsChanged FINAL)
    Q_PROPERTY(double bufferDurationSec READ bufferDurationSec NOTIFY statsChanged FINAL)

    // --- Sync quality metrics ---
    Q_PROPERTY(double lastSyncOffsetMs READ lastSyncOffsetMs NOTIFY statsChanged FINAL)
    Q_PROPERTY(double avgSyncOffsetMs READ avgSyncOffsetMs NOTIFY statsChanged FINAL)
    Q_PROPERTY(double clockDriftMs READ clockDriftMs NOTIFY statsChanged FINAL)
    Q_PROPERTY(double timeCorrectionMs READ timeCorrectionMs NOTIFY statsChanged FINAL)

    // --- Configuration / derived ---
    Q_PROPERTY(QString healthStatus READ healthStatus NOTIFY statsChanged FINAL)
    Q_PROPERTY(double samplingRate READ samplingRate NOTIFY samplingRateChanged FINAL)
    Q_PROPERTY(double samplesPerFrame READ samplesPerFrame NOTIFY samplingRateChanged FINAL)

    // --- Session tracking ---
    Q_PROPERTY(double sessionStartTime READ sessionStartTime NOTIFY sessionStartTimeChanged FINAL)
    Q_PROPERTY(bool isSessionActive READ isSessionActive NOTIFY sessionStartTimeChanged FINAL)
    Q_PROPERTY(int outOfRangeCount READ outOfRangeCount NOTIFY statsChanged FINAL)
    Q_PROPERTY(int totalQueryCount READ totalQueryCount NOTIFY statsChanged FINAL)

public:
    static EegSyncManager* instance();
    static EegSyncManager* create(QQmlEngine* qmlEngine, QJSEngine* jsEngine);

    explicit EegSyncManager(QObject* parent = nullptr);
    ~EegSyncManager();

    // -----------------------------------------------------------------------
    // Data input — called by EegBackend on the main thread
    // -----------------------------------------------------------------------

    /*
     * Appends a chunk of raw EEG samples to the rolling sync buffer.
     *
     * Only the channels listed in channelIndices are stored. This mirrors
     * the user's channel selection in the display, keeping sync data
     * consistent with what is shown and recorded.
     *
     * If channelIndices is empty, all hardware channels are stored.
     * The buffer is trimmed to m_maxBufferSize after each insertion.
     *
     * @param chunk          Raw EEG data [sample][channel] in μV
     * @param timestamps     LSL timestamp per sample (from lsl::pull_chunk)
     * @param channelIndices Selected channel indices into the chunk rows
     */
    void addEegSamples(const std::vector<std::vector<float>>& chunk,
                       const std::vector<double>& timestamps,
                       const QVector<int>& channelIndices);

    // -----------------------------------------------------------------------
    // Synchronization queries — called by VideoBackend / QML
    // -----------------------------------------------------------------------

    /*
     * Returns the EEG sample closest (or interpolated) to a video frame's
     * LSL timestamp. Applies the current time_correction() offset before
     * searching to compensate for EEG ↔ PC clock drift.
     *
     * Validates that the adjusted timestamp falls within the buffer range
     * before performing the search, and reports out-of-range conditions.
     *
     * Result keys:
     *   "valid"        — bool:   false if buffer is empty or timestamp invalid
     *   "timestamp"    — double: actual LSL timestamp of the matched sample
     *   "channels"     — QVariantList<double>: channel values in μV
     *   "offsetMs"     — double: |videoTs - matchedTs| in milliseconds
     *   "outOfRange"   — bool:   true if timestamp is outside buffer range
     *   "rangeErrorMs" — double: distance from nearest buffer boundary (ms),
     *                            only present when outOfRange is true
     *
     * Note: when outOfRange is true, "valid" may still be true if the nearest
     * boundary sample was returned as a fallback. Callers should check
     * outOfRange to decide whether to display a desynchronization warning.
     *
     * @param videoTimestamp  LSL timestamp stamped by lsl::local_clock()
     *                        at the moment the camera frame was captured
     */
    Q_INVOKABLE QVariantMap getEEGForFrame(double videoTimestamp) const;

    /*
     * Returns all EEG samples whose timestamps fall within [startTs, endTs].
     * Binary search is used to locate the start position (O(log N));
     * then a linear scan collects all samples until endTs.
     *
     * Suitable for retrieving all EEG data that corresponds to the
     * inter-frame interval between two consecutive video frames.
     */
    Q_INVOKABLE QVariantList getEEGRangeForFrame(double startTs, double endTs) const;

    // -----------------------------------------------------------------------
    // Configuration
    // -----------------------------------------------------------------------

    Q_INVOKABLE void setInterpolationMode(int mode); // 0=nearest, 1=linear
    Q_INVOKABLE void clearBuffer();

    // -----------------------------------------------------------------------
    // Session tracking — called by RecordingManager at session boundaries
    // -----------------------------------------------------------------------

    /*
     * Records the LSL timestamp at which the recording session started.
     * This provides a common reference point for session-relative time
     * calculations across both EEG and video streams. Must be called
     * once at the start of each recording session (from RecordingManager).
     */
    Q_INVOKABLE void markSessionStart();

    /*
     * Clears the session start timestamp and resets per-session counters
     * (out-of-range count, total query count). Called at session end.
     */
    Q_INVOKABLE void markSessionEnd();

    double sessionStartTime() const { return m_sessionStartTime; }
    bool isSessionActive() const { return m_sessionStartTime > 0.0; }

    // --- Diagnostic counters (per session) ---
    int outOfRangeCount() const { return m_outOfRangeCount; }
    int totalQueryCount() const { return m_totalQueryCount; }

    /*
     * Returns true if videoTimestamp falls within the current buffer range
     * [oldest - tolerance, newest + tolerance]. Tolerance is one inter-sample
     * interval (1/samplingRate) to account for rounding.
     *
     * This is a lightweight check that callers can use before getEEGForFrame()
     * to avoid wasting cycles on queries that would return "outOfRange".
     */
    Q_INVOKABLE bool isTimestampInRange(double videoTimestamp) const;

    /*
     * Called by EegBackend::onSamplingRateDetected() when the LSL stream
     * reports its nominal rate. Recalculates m_maxBufferSize to hold
     * exactly 30 seconds of data at the actual rate.
     */
    void setSamplingRate(double rate);
    double samplingRate() const { return m_samplingRate; }

    /* Expected number of EEG samples per video frame: samplingRate / videoFPS */
    double samplesPerFrame() const;

    int bufferSize() const;
    int maxBufferSize() const { return m_maxBufferSize; }
    void setMaxBufferSize(int size);

    double oldestTimestamp() const;
    double newestTimestamp() const;
    double bufferDurationSec() const;

    // Sync quality accessors
    double lastSyncOffsetMs() const { return m_lastSyncOffsetMs; }
    double avgSyncOffsetMs() const { return m_avgSyncOffsetMs; }
    double clockDriftMs() const { return m_clockDriftMs; }
    double timeCorrectionMs() const { return m_timeCorrectionMs * 1000.0; }

    /*
     * Health thresholds (empirical for clinical EEG-video synchronization):
     *   < 5 ms  → "SYNCED"  — acceptable for event marking
     *   5–15 ms → "WARNING" — drift accumulating, user should investigate
     *   > 15 ms → "DESYNC"  — synchronization unreliable
     */
    QString healthStatus() const;

    /*
     * Provides the LSL stream inlet used for time_correction() queries.
     * Must be called after the LSL stream is resolved (in AmplifierManager
     * after lsl::resolve_stream succeeds). Without this, m_timeCorrection
     * stays at 0.0 and no drift correction is applied.
     */
    void setLslInlet(lsl::stream_inlet* inlet);

signals:
    void statsChanged();
    void samplingRateChanged();
    void maxBufferSizeChanged();
    void sessionStartTimeChanged();

private:
    /* Performs a blocking time_correction() call (1 s timeout) to update
     * m_timeCorrection. Called once on setLslInlet() and then every 10 s
     * by m_timeCorrectionTimer to track long-term clock drift. */
    void updateTimeCorrection();

    /* O(log N) binary search returning the sample with the timestamp
     * closest to adjustedTs (EEG time base after drift correction). */
    EegTimestampedSample nearestNeighbor(double adjustedTs) const;

    /* Linear interpolation between the two samples bracketing adjustedTs.
     * Falls back to nearestNeighbor at buffer boundaries. */
    EegTimestampedSample linearInterpolate(double adjustedTs) const;

    /* Maintains a rolling average of sync offset over RUNNING_AVG_WINDOW
     * frames. Resets the accumulator once the window is filled to prevent
     * unbounded growth of m_offsetSum. */
    void updateRunningAverage(double offsetMs) const;

    static EegSyncManager* s_instance;

    mutable QMutex m_mutex;
    std::deque<EegTimestampedSample> m_buffer; // Sorted ascending by lslTimestamp
    int m_maxBufferSize = 7680;                // 30 s × 256 Hz default

    double m_samplingRate = 256.0;
    int m_interpolationMode = 0; // 0=nearest, 1=linear
    double m_videoFps = 30.0;

    // LSL clock drift correction
    lsl::stream_inlet* m_lslInlet = nullptr;
    double m_timeCorrection = 0.0;      // Current correction offset in seconds
    double m_prevTimeCorrection = 0.0;  // Previous value — used to compute drift rate
    QTimer* m_timeCorrectionTimer = nullptr;

    // Sync quality monitoring
    mutable double m_lastSyncOffsetMs = 0.0;
    mutable double m_avgSyncOffsetMs = 0.0;
    double m_clockDriftMs = 0.0;
    double m_timeCorrectionMs = 0.0;

    // Running average accumulators
    mutable int m_offsetSampleCount = 0;
    mutable double m_offsetSum = 0.0;
    static constexpr int RUNNING_AVG_WINDOW = 100;

    // Session tracking
    double m_sessionStartTime = 0.0;    // LSL timestamp at session start (0 = no active session)

    // Diagnostic counters (per session, reset on markSessionEnd)
    mutable int m_outOfRangeCount = 0;  // Number of getEEGForFrame() calls with timestamp outside buffer
    mutable int m_totalQueryCount = 0;  // Total getEEGForFrame() calls during session

    // Throttled stats notify timer — emits statsChanged() at 4 Hz to QML
    QTimer* m_statsTimer = nullptr;
};

#endif // EEGSYNCMANAGER_H
