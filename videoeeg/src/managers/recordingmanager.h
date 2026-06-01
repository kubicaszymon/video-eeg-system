/*
 * ==========================================================================
 *  recordingmanager.h — Recording Session Coordinator (Singleton)
 * ==========================================================================
 *
 *  PURPOSE:
 *    Coordinates all aspects of a long-term Video-EEG recording session:
 *    EEG data batching, video encoding, pause/resume lifecycle, disk space
 *    monitoring, and post-session summary generation. Acts as the single
 *    authoritative state machine for whether a session is active.
 *
 *  DESIGN PATTERNS:
 *    Singleton (QML_SINGLETON) — session state must be globally accessible
 *    from EegBackend (data writer), QML toolbar (controls), and VideoBackend.
 *    Command pattern — "request" signals carry typed data to the worker thread
 *    without using QMetaObject::invokeMethod strings (type-safe cross-thread).
 *
 *  THREADING MODEL:
 *
 *    Main Thread                       Worker Thread
 *    ──────────────                    ──────────────
 *    EegBackend::onDataReceived()
 *      → writeEegData()
 *          accumulates m_eegBatch
 *          (EEG_BATCH_SIZE = 100)
 *          → flushEegBatch()
 *              QMetaObject::invokeMethod(worker,
 *                  writeEegBatch, QueuedConnection)
 *                                          → RecordingWorker::writeEegBatch()
 *                                              → m_eegStream << rows
 *                                              → fsync
 *
 *    CameraManager::frameTimestampUpdated()
 *      → onFrameReady(lslTimestamp)
 *          emit requestWriteFrameTimestamp()
 *                                          → RecordingWorker::writeFrameTimestamp()
 *
 *    QML: stopRecording()
 *      → flushEegBatch() + stopVideoRecording()
 *          emit requestCloseFiles()
 *                                          → RecordingWorker::closeFiles()
 *                                              emit filesClosed(summary)
 *      ← onFilesClosed(summary)
 *          emit recordingStopped(...)    [QML displays summary dialog]
 *
 *  PAUSE/RESUME & VIDEO SEGMENTATION:
 *    On pauseRecording():
 *      1. Flush current EEG batch to disk (no data loss at boundary).
 *      2. Write PAUSE_START marker to both EEG and markers CSVs.
 *      3. Stop QMediaRecorder → closes current MKV segment.
 *    On resumeRecording():
 *      1. Accumulate paused wall-clock time in m_totalPausedDuration.
 *      2. Write PAUSE_STOP marker.
 *      3. Increment m_videoSegmentCount → new MKV filename (_seg002.mkv).
 *      4. Start new QMediaRecorder instance on the same capture session.
 *    sessionTimeSec() subtracts m_totalPausedDuration from elapsed LSL time,
 *    yielding continuous session-relative timestamps in the markers CSV.
 *
 *  EEG BATCHING:
 *    writeEegData() is called ~50 times/sec from EegBackend. Accumulating
 *    100 samples before flushing reduces syscalls from 50/sec to ~2-3/sec.
 *    flushEegBatch() uses QMetaObject::invokeMethod with a lambda capture
 *    rather than the requestWriteEegBatch signal, which avoids QueuedConnection
 *    silent-drop issues with nested QVector<QVector<float>> metatypes.
 *
 *  PENDING VIDEO START:
 *    startRecording() may be called before CameraManager::startCapture().
 *    In that case, m_pendingVideoStart=true and a one-shot connection to
 *    isCapturingChanged waits for the camera to become active before
 *    creating the QMediaRecorder. This handles the window startup race
 *    where RecordingManager is started from QML before the camera is live.
 *
 *  DATA FLOW SUMMARY:
 *    AmplifierManager → EegBackend → writeEegData() → batch → worker CSV
 *    CameraManager::frameTimestampUpdated() → onFrameReady() → worker CSV
 *    CameraManager::captureSession() → QMediaRecorder → MKV file
 *    Worker::filesClosed() → recordingStopped() → QML summary dialog
 *
 * ==========================================================================
 */

#ifndef RECORDINGMANAGER_H
#define RECORDINGMANAGER_H

#include <QObject>
#include <QThread>
#include <QTimer>
#include <QVector>
#include <QStringList>
#include <QQmlEngine>
#include <QtQml/qqmlregistration.h>
#include <QMediaRecorder>
#include <QMediaCaptureSession>
#include <QJsonObject>
#include <vector>
#include <lsl_cpp.h>

#include "sessionconfig.h"
#include "recordingsummary.h"

class RecordingWorker;

class RecordingManager : public QObject
{
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

    Q_PROPERTY(bool isRecording READ isRecording NOTIFY isRecordingChanged FINAL)
    Q_PROPERTY(bool isPaused READ isPaused NOTIFY isPausedChanged FINAL)
    Q_PROPERTY(qint64 recordedSamples READ recordedSamples NOTIFY statsUpdated FINAL)
    Q_PROPERTY(qint64 recordedFrames READ recordedFrames NOTIFY statsUpdated FINAL)
    Q_PROPERTY(double recordedDurationSec READ recordedDurationSec NOTIFY statsUpdated FINAL)
    Q_PROPERTY(qint64 eegFileSizeBytes READ eegFileSizeBytes NOTIFY statsUpdated FINAL)
    Q_PROPERTY(qint64 videoFileSizeBytes READ videoFileSizeBytes NOTIFY statsUpdated FINAL)
    Q_PROPERTY(qint64 diskSpaceMB READ diskSpaceMB NOTIFY statsUpdated FINAL)
    Q_PROPERTY(bool diskSpaceWarning READ diskSpaceWarning NOTIFY diskSpaceWarningChanged FINAL)
    Q_PROPERTY(double estimatedRemainingHours READ estimatedRemainingHours NOTIFY statsUpdated FINAL)

public:
    static RecordingManager* instance();
    static RecordingManager* create(QQmlEngine* qmlEngine, QJSEngine* jsEngine);

    explicit RecordingManager(QObject* parent = nullptr);
    ~RecordingManager();

    // -----------------------------------------------------------------------
    // Session control — called from QML toolbar buttons
    // -----------------------------------------------------------------------

    /* Validates the save path, checks disk space, starts the worker thread,
     * initializes CSV files, and optionally starts video recording.
     * Returns false (and emits recordingError) if preconditions are not met.
     * The worker thread is recreated fresh for each session. */
    Q_INVOKABLE bool startRecording(const QString& saveFolderPath,
                                    const QString& sessionName,
                                    const QStringList& channelNames,
                                    const QString& cameraId,
                                    double samplingRate);

    /* Flushes current EEG batch, writes PAUSE_START markers, stops video.
     * EEG data received while paused is silently discarded (isPaused guard
     * in writeEegData). */
    Q_INVOKABLE void pauseRecording();

    /* Resumes after pause: accumulates paused duration, writes PAUSE_STOP,
     * starts a new video segment (m_videoSegmentCount++). */
    Q_INVOKABLE void resumeRecording();

    /* Flushes remaining EEG data, stops video, disconnects camera signals,
     * sums MKV segment sizes, and delegates file closure to the worker.
     * The recordingStopped() signal fires asynchronously after the worker
     * emits filesClosed() (which may be seconds later on slow media). */
    Q_INVOKABLE void stopRecording();

    // -----------------------------------------------------------------------
    // Data input — called from EegBackend on the main thread (hot path)
    // -----------------------------------------------------------------------

    /* Accumulates incoming EEG chunk into m_eegBatch. Flushes the batch
     * to the worker thread when EEG_BATCH_SIZE (100 samples) is reached.
     * No-op when not recording or paused — guard is a branch on m_isRecording
     * and m_isPaused which is very cheap. */
    void writeEegData(const std::vector<std::vector<float>>& chunk,
                      const std::vector<double>& timestamps,
                      const QVector<int>& channelIndices);

    /* Immediately routes a single event marker to the worker (no batching).
     * Markers are time-critical and low-frequency so immediate dispatch is safe. */
    void writeMarker(const QString& type, const QString& label, double lslTimestamp);

    // --- State ---

    bool isRecording() const { return m_isRecording; }
    bool isPaused() const { return m_isPaused; }
    qint64 recordedSamples() const { return m_recordedSamples; }
    qint64 recordedFrames() const { return m_recordedFrames; }
    double recordedDurationSec() const;
    qint64 eegFileSizeBytes() const { return m_eegFileSize; }
    qint64 videoFileSizeBytes() const { return m_videoFileSize; }
    qint64 diskSpaceMB() const;

    Q_INVOKABLE bool checkDiskSpace(const QString& path, qint64 requiredMB = 500);

    bool diskSpaceWarning() const { return m_diskSpaceWarning; }
    double estimatedRemainingHours() const;

    // -----------------------------------------------------------------
    // Crash recovery (Auto-Resume)
    // -----------------------------------------------------------------

    /* Scans a folder for any _session_state.json with status != "closed".
     * Returns a QVariantMap with the session state if found, empty otherwise.
     * Called from QML/AmplifierSetupBackend at startup. */
    Q_INVOKABLE QVariantMap checkForUnfinishedSession(const QString& folderPath) const;

signals:
    void isRecordingChanged();
    void isPausedChanged();
    void statsUpdated();
    void diskSpaceWarningChanged();
    void recordingStarted(const QString& sessionName);
    void recordingStopped(const QString& sessionName,
                         const QString& savePath,
                         const QString& duration,
                         const QString& eegSize,
                         const QString& videoSize,
                         qint64 eegSamples,
                         qint64 videoFrames,
                         int markerCount);
    void recordingError(const QString& error);
    /* Emitted when disk space drops below the warning threshold (5 GB)
     * but has not yet hit the critical threshold (1 GB). QML shows
     * an amber banner. Carries remaining MB for display. */
    void diskSpaceLow(qint64 remainingMB);

    // -----------------------------------------------------------------------
    // Command signals — used as a type-safe cross-thread RPC mechanism.
    // These signals are connected to the worker's public slots with
    // Qt::QueuedConnection. Emitting them from the main thread posts a
    // message to the worker thread's event queue without blocking.
    // NOTE: The EEG batch flush uses QMetaObject::invokeMethod instead
    // (see flushEegBatch()) to avoid metatype registration complexity
    // with nested QVector<QVector<float>>.
    // -----------------------------------------------------------------------
    void requestInitFiles(const QString& eegPath, const QString& markersPath,
                          const QString& framesPath, const QString& metadataPath,
                          const QStringList& channelNames, const QString& sessionName,
                          double samplingRate);
    void requestWriteEegBatch(const QVector<QVector<float>>& samples,
                              const QVector<double>& timestamps);
    void requestWritePauseMarker(const QString& type, double lslTimestamp, double sessionTimeSec);
    void requestWriteMarker(const QString& type, const QString& label,
                            double lslTimestamp, double sessionTimeSec);
    void requestWriteFrameTimestamp(double lslTimestamp, qint64 frameNumber,
                                    const QString& segmentFile);
    void requestCloseFiles(double durationSeconds, qint64 videoFileSizeBytes);

    // Session state persistence command signals (cross-thread to worker)
    void requestWriteSessionState(const QJsonObject& stateJson, const QString& statePath);
    void requestMarkSessionClosed(const QString& statePath);

private slots:
    void onFilesInitialized(bool success, const QString& error);
    void onBatchWritten(int sampleCount, qint64 eegFileSize);
    void onFilesClosed(const RecordingSummary& summary);
    void onWorkerError(const QString& error);
    void onFrameReady(double lslTimestamp);
    void onFlushTimer();
    void onDiskCheckTimer();
    void onStatsTimer();
    void onCameraCapturingChanged();

private:
    void flushEegBatch();
    void startVideoRecording();
    void stopVideoRecording();
    double sessionTimeSec(double lslTimestamp) const;
    void cleanupWorkerThread();
    void persistSessionState();
    QJsonObject buildSessionStateJson() const;

    static RecordingManager* s_instance;

    // Worker thread
    QThread* m_workerThread = nullptr;
    RecordingWorker* m_worker = nullptr;

    // Video recording
    QMediaRecorder* m_videoRecorder = nullptr;

    // Session config
    SessionConfig m_config;
    bool m_isRecording = false;
    bool m_isPaused = false;

    // Session timing (all in LSL seconds)
    double m_sessionStartLslTime  = 0.0; // lsl::local_clock() at startRecording()
    double m_pauseStartLslTime    = 0.0; // lsl::local_clock() at pauseRecording()
    double m_totalPausedDuration  = 0.0; // Sum of all completed pause intervals
    int    m_videoSegmentCount    = 1;   // Increments on each resumeRecording()
    bool   m_pendingVideoStart    = false; // True if waiting for camera to start

    // EEG batching — accumulate samples to reduce disk I/O frequency
    QVector<QVector<float>> m_eegBatch;
    QVector<double>         m_timestampBatch;
    static constexpr int EEG_BATCH_SIZE = 100; // ~0.4 s at 256 Hz

    // Live statistics — updated by worker callbacks and stats timer
    qint64 m_recordedSamples = 0;
    qint64 m_recordedFrames  = 0;
    qint64 m_eegFileSize     = 0;
    qint64 m_videoFileSize   = 0;

    // Periodic maintenance timers
    QTimer* m_flushTimer     = nullptr; // Forces EEG batch flush every 5 s
    QTimer* m_diskCheckTimer = nullptr; // Checks free disk space every 60 s
    QTimer* m_statsTimer     = nullptr; // Refreshes UI statistics every 1 s

    // Disk space watchdog — two-level threshold system
    bool m_diskSpaceWarning = false;
    static constexpr qint64 DISK_WARNING_MB  = 5000; // 5 GB — amber warning banner
    static constexpr qint64 DISK_CRITICAL_MB = 1000; // 1 GB — hard stop
    static constexpr int DISK_CHECK_INTERVAL_MS = 60 * 1000; // 60 seconds
};

#endif // RECORDINGMANAGER_H
