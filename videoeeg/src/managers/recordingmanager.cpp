/*
 * ==========================================================================
 *  recordingmanager.cpp — Recording Session Coordinator Implementation
 * ==========================================================================
 *  See recordingmanager.h for the full architecture overview, threading model,
 *  pause/resume video segmentation design, and EEG batching rationale.
 * ==========================================================================
 */

#include "recordingmanager.h"
#include "recordingworker.h"
#include "cameramanager.h"
#include "eegsyncmanager.h"

#include <QDir>
#include <QDirIterator>
#include <QStorageInfo>
#include <QFileInfo>
#include <QMediaFormat>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QDateTime>
#include <QDebug>

RecordingManager* RecordingManager::s_instance = nullptr;

RecordingManager* RecordingManager::instance()
{
    if (!s_instance)
        s_instance = new RecordingManager();
    return s_instance;
}

RecordingManager* RecordingManager::create(QQmlEngine* qmlEngine, QJSEngine* jsEngine)
{
    Q_UNUSED(jsEngine)
    auto* inst = instance();
    QJSEngine::setObjectOwnership(inst, QJSEngine::CppOwnership);
    if (qmlEngine)
        qmlEngine->setObjectOwnership(inst, QQmlEngine::CppOwnership);
    return inst;
}

RecordingManager::RecordingManager(QObject* parent)
    : QObject(parent)
{
    // CRITICAL — Qt 6 singleton double-construction guard:
    // QML_SINGLETON + the create() factory pattern can result in two instances:
    // one created early by C++ code calling instance(), and one created later
    // by the QML engine calling create(). The QML engine's instance must win
    // because it is the one QML property bindings will hold a reference to.
    // We delete the old C++ instance and redirect s_instance to this object.
    if (s_instance && s_instance != this) {
        qDebug() << "[RecordingManager] Replacing old C++ instance with QML instance";
        delete s_instance;
    }
    s_instance = this;

    // Register all complex types that cross thread boundaries via QueuedConnection.
    // Without registration, Qt silently drops signals carrying these types.
    // See MEMORY.md: "Qt::QueuedConnection signals with complex types are
    // silently dropped unless registered with qRegisterMetaType<T>()."
    qRegisterMetaType<RecordingSummary>("RecordingSummary");
    qRegisterMetaType<QVector<QVector<float>>>("QVector<QVector<float>>");
    qRegisterMetaType<QVector<double>>("QVector<double>");
    qRegisterMetaType<QVector<float>>("QVector<float>");
    qRegisterMetaType<QJsonObject>("QJsonObject");

    // Flush timer - forces EEG batch write every 5 seconds
    m_flushTimer = new QTimer(this);
    m_flushTimer->setInterval(5000);
    connect(m_flushTimer, &QTimer::timeout, this, &RecordingManager::onFlushTimer);

    // Disk check timer — checks free space every 60 seconds.
    // Reduced from 5 minutes because a 1080p30 + EEG stream can consume
    // 3-5 GB/hour, making 5-minute intervals too infrequent for early warning.
    m_diskCheckTimer = new QTimer(this);
    m_diskCheckTimer->setInterval(DISK_CHECK_INTERVAL_MS);
    connect(m_diskCheckTimer, &QTimer::timeout, this, &RecordingManager::onDiskCheckTimer);

    // Stats timer - updates UI stats every second
    m_statsTimer = new QTimer(this);
    m_statsTimer->setInterval(1000);
    connect(m_statsTimer, &QTimer::timeout, this, &RecordingManager::onStatsTimer);
}

RecordingManager::~RecordingManager()
{
    if (m_isRecording)
        stopRecording();
    cleanupWorkerThread();
}

bool RecordingManager::startRecording(const QString& saveFolderPath,
                                       const QString& sessionName,
                                       const QStringList& channelNames,
                                       const QString& cameraId,
                                       double samplingRate)
{
    if (m_isRecording) {
        qWarning() << "[RecordingManager] Already recording";
        return false;
    }

    // Validate folder
    QDir saveDir(saveFolderPath);
    if (!saveDir.exists()) {
        if (!saveDir.mkpath(".")) {
            emit recordingError("Cannot create save folder: " + saveFolderPath);
            return false;
        }
    }

    // Check disk space (need at least 500 MB)
    if (!checkDiskSpace(saveFolderPath, 500)) {
        emit recordingError("Insufficient disk space. Need at least 500 MB free.");
        return false;
    }

    // Configure session
    m_config.saveFolderPath = saveFolderPath;
    m_config.sessionName = sessionName;
    m_config.channelNames = channelNames;
    m_config.cameraId = cameraId;
    m_config.samplingRate = samplingRate;

    // Reset state
    m_sessionStartLslTime = lsl::local_clock();
    m_totalPausedDuration = 0.0;
    m_pauseStartLslTime = 0.0;
    m_videoSegmentCount = 1;
    m_pendingVideoStart = false;
    m_recordedSamples = 0;

    // Notify EegSyncManager that a recording session has started.
    // This enables session-relative time tracking and resets per-session
    // diagnostic counters (out-of-range queries, total query count).
    EegSyncManager::instance()->markSessionStart();
    m_recordedFrames = 0;
    m_eegFileSize = 0;
    m_videoFileSize = 0;
    m_eegBatch.clear();
    m_timestampBatch.clear();

    // Create worker thread
    cleanupWorkerThread();
    m_workerThread = new QThread(this);
    m_worker = new RecordingWorker();
    m_worker->moveToThread(m_workerThread);

    // Connect worker response signals
    connect(m_worker, &RecordingWorker::filesInitialized,
            this, &RecordingManager::onFilesInitialized, Qt::QueuedConnection);
    connect(m_worker, &RecordingWorker::batchWritten,
            this, &RecordingManager::onBatchWritten, Qt::QueuedConnection);
    connect(m_worker, &RecordingWorker::filesClosed,
            this, &RecordingManager::onFilesClosed, Qt::QueuedConnection);
    connect(m_worker, &RecordingWorker::errorOccurred,
            this, &RecordingManager::onWorkerError, Qt::QueuedConnection);

    // Connect command signals to worker slots (type-safe, no invokeMethod)
    connect(this, &RecordingManager::requestInitFiles,
            m_worker, &RecordingWorker::initializeFiles, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestWriteEegBatch,
            m_worker, &RecordingWorker::writeEegBatch, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestWritePauseMarker,
            m_worker, &RecordingWorker::writePauseMarker, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestWriteMarker,
            m_worker, &RecordingWorker::writeMarker, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestWriteFrameTimestamp,
            m_worker, &RecordingWorker::writeFrameTimestamp, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestCloseFiles,
            m_worker, &RecordingWorker::closeFiles, Qt::QueuedConnection);

    // Session state persistence (crash recovery / Auto-Resume)
    connect(this, &RecordingManager::requestWriteSessionState,
            m_worker, &RecordingWorker::writeSessionState, Qt::QueuedConnection);
    connect(this, &RecordingManager::requestMarkSessionClosed,
            m_worker, &RecordingWorker::markSessionClosed, Qt::QueuedConnection);

    // Clean up worker when thread finishes
    connect(m_workerThread, &QThread::finished, m_worker, &QObject::deleteLater);

    m_workerThread->start();

    // Initialize files via signal (type-safe cross-thread)
    emit requestInitFiles(m_config.eegFilePath(),
                          m_config.markersFilePath(),
                          m_config.framesFilePath(),
                          m_config.metadataFilePath(),
                          channelNames,
                          sessionName,
                          samplingRate);

    // Start video recording if camera is selected
    if (!cameraId.isEmpty()) {
        auto* cam = CameraManager::instance();

        // Connect frame timestamps for sync CSV
        connect(cam, &CameraManager::frameTimestampUpdated,
                this, [this]() {
            onFrameReady(CameraManager::instance()->lastFrameTimestamp());
        });

        // Start video recorder only when camera is actually capturing
        if (cam->isCapturing()) {
            startVideoRecording();
        } else {
            m_pendingVideoStart = true;
            connect(cam, &CameraManager::isCapturingChanged,
                    this, &RecordingManager::onCameraCapturingChanged);
            qDebug() << "[RecordingManager] Waiting for camera to start capturing...";
        }
    }

    m_isRecording = true;
    m_isPaused = false;
    emit isRecordingChanged();
    emit isPausedChanged();

    // Start timers
    m_flushTimer->start();
    m_diskCheckTimer->start();
    m_statsTimer->start();

    // Persist initial session state immediately so a crash at any point
    // after this line will be detectable on the next launch.
    persistSessionState();

    qDebug() << "[RecordingManager] Recording started:" << sessionName
             << "this:" << this << "s_instance:" << s_instance;
    emit recordingStarted(sessionName);
    return true;
}

void RecordingManager::pauseRecording()
{
    if (!m_isRecording || m_isPaused)
        return;

    m_isPaused = true;
    m_pauseStartLslTime = lsl::local_clock();

    // Flush any pending EEG data before pause
    flushEegBatch();

    // Write pause marker
    double sessTime = sessionTimeSec(m_pauseStartLslTime);
    emit requestWritePauseMarker("PAUSE_START", m_pauseStartLslTime, sessTime);

    // Stop video recording
    stopVideoRecording();

    emit isPausedChanged();
    qDebug() << "[RecordingManager] Recording paused at LSL:" << m_pauseStartLslTime;
}

void RecordingManager::resumeRecording()
{
    if (!m_isRecording || !m_isPaused)
        return;

    double resumeTime = lsl::local_clock();
    m_totalPausedDuration += (resumeTime - m_pauseStartLslTime);
    m_isPaused = false;

    // Write resume marker
    double sessTime = sessionTimeSec(resumeTime);
    emit requestWritePauseMarker("PAUSE_STOP", resumeTime, sessTime);

    // Start new video segment
    if (!m_config.cameraId.isEmpty()) {
        m_videoSegmentCount++;
        startVideoRecording();
    }

    emit isPausedChanged();
    qDebug() << "[RecordingManager] Recording resumed. Total paused:" << m_totalPausedDuration << "s";
}

void RecordingManager::stopRecording()
{
    if (!m_isRecording)
        return;

    // If paused, account for final pause duration
    if (m_isPaused) {
        m_totalPausedDuration += (lsl::local_clock() - m_pauseStartLslTime);
        m_isPaused = false;
    }

    // Flush remaining EEG data
    flushEegBatch();

    // Stop video
    stopVideoRecording();

    // Disconnect camera signals
    if (!m_config.cameraId.isEmpty()) {
        auto* cam = CameraManager::instance();
        disconnect(cam, &CameraManager::frameTimestampUpdated, this, nullptr);
        disconnect(cam, &CameraManager::isCapturingChanged,
                   this, &RecordingManager::onCameraCapturingChanged);
        m_pendingVideoStart = false;
    }

    // Calculate video file size (sum of all segments)
    qint64 totalVideoSize = 0;
    for (int seg = 1; seg <= m_videoSegmentCount; ++seg) {
        QFileInfo fi(m_config.videoSegmentFilePath(seg));
        if (fi.exists())
            totalVideoSize += fi.size();
    }
    m_videoFileSize = totalVideoSize;

    // Close files on worker thread
    double duration = recordedDurationSec();
    emit requestCloseFiles(duration, totalVideoSize);

    // Mark the session as cleanly closed in the state file.
    // This is the final write — if the app crashed *before* this point,
    // the state file would still say "recording", enabling Auto-Resume.
    emit requestMarkSessionClosed(m_config.sessionStateFilePath());

    m_isRecording = false;
    emit isRecordingChanged();
    emit isPausedChanged();

    // Reset disk space warning
    if (m_diskSpaceWarning) {
        m_diskSpaceWarning = false;
        emit diskSpaceWarningChanged();
    }

    // Notify EegSyncManager that the session has ended. Logs per-session
    // diagnostic summary (total queries, out-of-range ratio) and resets counters.
    EegSyncManager::instance()->markSessionEnd();

    // Stop timers
    m_flushTimer->stop();
    m_diskCheckTimer->stop();
    m_statsTimer->stop();

    qDebug() << "[RecordingManager] Recording stopped. Duration:" << duration << "s";
}

void RecordingManager::writeEegData(const std::vector<std::vector<float>>& chunk,
                                     const std::vector<double>& timestamps,
                                     const QVector<int>& channelIndices)
{
    static int callCount = 0;
    if (++callCount <= 5) {
        qDebug() << "[RecordingManager] writeEegData call#" << callCount
                 << "isRecording:" << m_isRecording
                 << "this:" << this << "s_instance:" << s_instance
                 << "chunk:" << chunk.size() << "chIdx:" << channelIndices.size();
    }

    if (!m_isRecording || m_isPaused)
        return;

    // Extract selected channels and add to batch
    for (size_t i = 0; i < chunk.size(); ++i) {
        QVector<float> selectedChannels;
        selectedChannels.reserve(channelIndices.size());

        for (int chIdx : channelIndices) {
            if (chIdx < static_cast<int>(chunk[i].size()))
                selectedChannels.append(chunk[i][chIdx]);
            else
                selectedChannels.append(0.0f);
        }

        m_eegBatch.append(selectedChannels);
        m_timestampBatch.append(timestamps[i]);
    }

    // Flush when batch is full
    if (m_eegBatch.size() >= EEG_BATCH_SIZE) {
        flushEegBatch();
    }
}

void RecordingManager::writeMarker(const QString& type, const QString& label,
                                    double lslTimestamp)
{
    if (!m_isRecording || !m_worker)
        return;

    double sessTime = sessionTimeSec(lslTimestamp);
    emit requestWriteMarker(type, label, lslTimestamp, sessTime);
}

double RecordingManager::recordedDurationSec() const
{
    if (!m_isRecording)
        return 0.0;

    double now = lsl::local_clock();
    double totalElapsed = now - m_sessionStartLslTime;
    double pausedNow = m_isPaused ? (now - m_pauseStartLslTime) : 0.0;
    return totalElapsed - m_totalPausedDuration - pausedNow;
}

qint64 RecordingManager::diskSpaceMB() const
{
    if (m_config.saveFolderPath.isEmpty())
        return -1;
    QStorageInfo storage(m_config.saveFolderPath);
    return storage.bytesAvailable() / (1024 * 1024);
}

bool RecordingManager::checkDiskSpace(const QString& path, qint64 requiredMB)
{
    QStorageInfo storage(path);
    if (!storage.isValid())
        return false;
    qint64 availableMB = storage.bytesAvailable() / (1024 * 1024);
    return availableMB >= requiredMB;
}

// --- Private slots ---

void RecordingManager::onFilesInitialized(bool success, const QString& error)
{
    if (!success) {
        qWarning() << "[RecordingManager] File init failed:" << error;
        emit recordingError(error);
        stopRecording();
    } else {
        qDebug() << "[RecordingManager] Files initialized successfully";
    }
}

void RecordingManager::onBatchWritten(int sampleCount, qint64 eegFileSize)
{
    m_recordedSamples += sampleCount;
    m_eegFileSize = eegFileSize;
}

void RecordingManager::onFilesClosed(const RecordingSummary& summary)
{
    qDebug() << "[RecordingManager] Summary - EEG:" << summary.eegSizeFormatted()
             << "Video:" << summary.videoSizeFormatted()
             << "Duration:" << summary.durationFormatted();

    emit recordingStopped(summary.sessionName,
                         summary.savePath,
                         summary.durationFormatted(),
                         summary.eegSizeFormatted(),
                         summary.videoSizeFormatted(),
                         summary.eegSamples,
                         summary.videoFrames,
                         summary.markerCount);

    cleanupWorkerThread();
}

void RecordingManager::onWorkerError(const QString& error)
{
    qWarning() << "[RecordingManager] Worker error:" << error;
    emit recordingError(error);
}

void RecordingManager::onFrameReady(double lslTimestamp)
{
    if (!m_isRecording || m_isPaused || !m_worker)
        return;

    m_recordedFrames++;
    QString segmentFile = QFileInfo(m_config.videoSegmentFilePath(m_videoSegmentCount)).fileName();

    emit requestWriteFrameTimestamp(lslTimestamp, m_recordedFrames, segmentFile);
}

void RecordingManager::onFlushTimer()
{
    if (!m_eegBatch.isEmpty()) {
        flushEegBatch();
    }

    // Piggy-back session state persistence on the 5-second flush timer.
    // This ensures the state file is always within 5 seconds of the actual
    // recording progress. On crash, at most 5 seconds of state is lost.
    if (m_isRecording) {
        persistSessionState();
    }
}

void RecordingManager::onDiskCheckTimer()
{
    if (!m_isRecording)
        return;

    qint64 freeMB = diskSpaceMB();
    if (freeMB < 0)
        return;

    // Level 1: Critical — stop recording immediately to prevent data corruption
    if (freeMB < DISK_CRITICAL_MB) {
        qWarning() << "[RecordingManager] CRITICAL disk space:" << freeMB << "MB — stopping recording";
        emit recordingError(QString("Critical: only %1 MB remaining. Recording stopped to protect data.").arg(freeMB));
        stopRecording();
        return;
    }

    // Level 2: Warning — show amber banner but continue recording
    bool wasWarning = m_diskSpaceWarning;
    m_diskSpaceWarning = (freeMB < DISK_WARNING_MB);

    if (m_diskSpaceWarning && !wasWarning) {
        qWarning() << "[RecordingManager] Low disk space warning:" << freeMB << "MB";
        emit diskSpaceLow(freeMB);
    }

    if (m_diskSpaceWarning != wasWarning) {
        emit diskSpaceWarningChanged();
    }
}

void RecordingManager::onStatsTimer()
{
    // Update video file size
    if (!m_config.cameraId.isEmpty()) {
        qint64 totalVideoSize = 0;
        for (int seg = 1; seg <= m_videoSegmentCount; ++seg) {
            QFileInfo fi(m_config.videoSegmentFilePath(seg));
            if (fi.exists())
                totalVideoSize += fi.size();
        }
        m_videoFileSize = totalVideoSize;
    }

    emit statsUpdated();
}

void RecordingManager::onCameraCapturingChanged()
{
    auto* cam = CameraManager::instance();
    if (cam->isCapturing() && m_pendingVideoStart && m_isRecording) {
        m_pendingVideoStart = false;
        startVideoRecording();
        disconnect(cam, &CameraManager::isCapturingChanged,
                   this, &RecordingManager::onCameraCapturingChanged);
        qDebug() << "[RecordingManager] Camera now capturing, video recording started";
    }
}

// --- Private methods ---

void RecordingManager::flushEegBatch()
{
    if (m_eegBatch.isEmpty() || !m_worker)
        return;

    // Lambda capture approach instead of emit requestWriteEegBatch():
    // QVector<QVector<float>> is a nested template type. Even after
    // qRegisterMetaType<QVector<QVector<float>>>(), Qt's queued signal
    // delivery can silently drop the payload if the argument type is not
    // recognized correctly by the meta-object system.
    // Capturing the data by value in a lambda and using invokeMethod with
    // Qt::QueuedConnection sidesteps the metatype machinery entirely —
    // the lambda owns the data and delivers it directly to the worker slot.
    QVector<QVector<float>> batchCopy      = m_eegBatch;
    QVector<double>         timestampsCopy = m_timestampBatch;
    RecordingWorker*        worker         = m_worker;

    QMetaObject::invokeMethod(worker, [worker, batchCopy, timestampsCopy]() {
        worker->writeEegBatch(batchCopy, timestampsCopy);
    }, Qt::QueuedConnection);

    m_eegBatch.clear();
    m_timestampBatch.clear();
}

void RecordingManager::startVideoRecording()
{
    auto* cameraMgr = CameraManager::instance();
    if (!cameraMgr || !cameraMgr->captureSession())
        return;

    // Create recorder
    if (m_videoRecorder) {
        delete m_videoRecorder;
        m_videoRecorder = nullptr;
    }

    m_videoRecorder = new QMediaRecorder(this);
    cameraMgr->captureSession()->setRecorder(m_videoRecorder);

    // H.264 in Matroska (MKV) container:
    // H.264 chosen for broad hardware encoder support (NVENC, Intel QSV, VA-API)
    // and near-universal playback compatibility in clinical review software.
    // Matroska (MKV) chosen over MP4 because MKV containers are recoverable
    // after an unclean close (power loss), while MP4 requires the moov atom
    // to be written at the end — a partially written MP4 is unplayable.
    QMediaFormat format;
    format.setFileFormat(QMediaFormat::Matroska);
    format.setVideoCodec(QMediaFormat::VideoCodec::H264);
    m_videoRecorder->setMediaFormat(format);
    m_videoRecorder->setQuality(QMediaRecorder::HighQuality);

    // Set output location
    QString videoPath = m_config.videoSegmentFilePath(m_videoSegmentCount);
    m_videoRecorder->setOutputLocation(QUrl::fromLocalFile(videoPath));

    // Connect error signal
    connect(m_videoRecorder, &QMediaRecorder::errorOccurred,
            this, [this](QMediaRecorder::Error error, const QString& errorString) {
        Q_UNUSED(error)
        qWarning() << "[RecordingManager] Video recorder error:" << errorString;
        emit recordingError("Video recording error: " + errorString);
    });

    m_videoRecorder->record();
    qDebug() << "[RecordingManager] Video recording started:" << videoPath;
}

void RecordingManager::stopVideoRecording()
{
    if (m_videoRecorder) {
        m_videoRecorder->stop();
        qDebug() << "[RecordingManager] Video recording stopped";
    }
}

double RecordingManager::sessionTimeSec(double lslTimestamp) const
{
    // Converts an absolute LSL timestamp to a session-relative time in seconds
    // with paused intervals excluded. This gives the "recording clock" value
    // written to the markers and frames CSVs — it matches what a human reading
    // the EEG waveform would see on the time axis, skipping over paused segments.
    double elapsed = lslTimestamp - m_sessionStartLslTime;
    return elapsed - m_totalPausedDuration;
}

void RecordingManager::cleanupWorkerThread()
{
    if (m_workerThread) {
        m_workerThread->quit();
        m_workerThread->wait(5000);
        delete m_workerThread;
        m_workerThread = nullptr;
        m_worker = nullptr; // Deleted by QThread::finished -> deleteLater
    }
}

// ==========================================================================
//  Session State Persistence (Crash Recovery / Auto-Resume)
// ==========================================================================

QJsonObject RecordingManager::buildSessionStateJson() const
{
    QJsonObject state;
    state["status"] = m_isPaused ? QStringLiteral("paused") : QStringLiteral("recording");
    state["sessionName"] = m_config.sessionName;
    state["saveFolderPath"] = m_config.saveFolderPath;
    state["amplifierId"] = m_config.amplifierId;
    state["cameraId"] = m_config.cameraId;
    state["samplingRate"] = m_config.samplingRate;

    QJsonArray chNames;
    for (const auto& name : m_config.channelNames)
        chNames.append(name);
    state["channelNames"] = chNames;

    QJsonArray chIndices;
    for (int idx : m_config.channels)
        chIndices.append(idx);
    state["channels"] = chIndices;

    state["sessionStartLslTime"] = m_sessionStartLslTime;
    state["lastLslTimestamp"] = lsl::local_clock();
    state["lastWallClock"] = QDateTime::currentDateTime().toString(Qt::ISODate);
    state["totalPausedDuration"] = m_totalPausedDuration;
    state["videoSegmentCount"] = m_videoSegmentCount;
    state["recordedSamples"] = m_recordedSamples;
    state["recordedFrames"] = m_recordedFrames;
    state["eegFileSizeBytes"] = m_eegFileSize;
    state["videoFileSizeBytes"] = m_videoFileSize;
    state["schemaVersion"] = QStringLiteral("1.0");

    return state;
}

void RecordingManager::persistSessionState()
{
    if (!m_isRecording || !m_worker)
        return;

    QJsonObject state = buildSessionStateJson();
    emit requestWriteSessionState(state, m_config.sessionStateFilePath());
}

// ==========================================================================
//  Crash Detection — called from QML at startup
// ==========================================================================

QVariantMap RecordingManager::checkForUnfinishedSession(const QString& folderPath) const
{
    QDir dir(folderPath);
    if (!dir.exists())
        return {};

    // Scan for any _session_state.json file with status != "closed"
    QStringList filters;
    filters << "*_session_state.json";
    QFileInfoList stateFiles = dir.entryInfoList(filters, QDir::Files, QDir::Time);

    for (const QFileInfo& fi : stateFiles) {
        QFile file(fi.absoluteFilePath());
        if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
            continue;

        QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
        file.close();

        if (!doc.isObject())
            continue;

        QJsonObject state = doc.object();
        QString status = state.value("status").toString();

        // "closed" means the session ended cleanly — skip it
        if (status == "closed")
            continue;

        // Found an unfinished session (status is "recording" or "paused")
        qDebug() << "[RecordingManager] Unfinished session found:" << fi.fileName()
                 << "status:" << status;
        return state.toVariantMap();
    }

    return {};
}

// ==========================================================================
//  Estimated Remaining Recording Time
// ==========================================================================

double RecordingManager::estimatedRemainingHours() const
{
    if (!m_isRecording)
        return -1.0;

    double elapsed = recordedDurationSec();
    if (elapsed < 30.0)
        return -1.0; // Not enough data to estimate

    // Calculate bytes per second from observed EEG + video growth
    double totalBytes = static_cast<double>(m_eegFileSize + m_videoFileSize);
    double bytesPerSec = totalBytes / elapsed;

    if (bytesPerSec < 1.0)
        return -1.0; // Avoid division by zero

    qint64 freeBytes = diskSpaceMB() * 1024LL * 1024LL;
    double remainingSec = static_cast<double>(freeBytes) / bytesPerSec;
    return remainingSec / 3600.0;
}
