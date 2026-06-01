/*
 * ==========================================================================
 *  VideoBackend.h — Video Display ViewModel
 * ==========================================================================
 *
 *  PURPOSE:
 *    The ViewModel for the video display window (VideoDisplayWindow.qml).
 *    Acts as the thin adapter layer between the global CameraManager singleton
 *    (hardware) and the per-window UI state (capture status, statistics,
 *    synchronization API).
 *
 *  DESIGN PATTERN:
 *    MVVM ViewModel (QML_ELEMENT) — created per-window by QML.
 *    Adapter — proxies CameraManager's signals into a QML-friendly interface
 *    and adds a local ring buffer of VideoFramePackets for sync queries.
 *
 *  RELATIONSHIP TO CameraManager:
 *    VideoBackend does NOT own the camera; CameraManager does. This means:
 *      • Multiple VideoBackend instances would all share the same camera feed
 *        (though only one window is expected in practice).
 *      • stopCapture() delegates to CameraManager::stopCapture(); the camera
 *        hardware actually stops only if no other consumer holds it active.
 *      • m_isCapturing reflects CameraManager's state, not an independent one.
 *
 *  FRAME BUFFER & SYNCHRONIZATION API:
 *    Every incoming VideoFramePacket is stored in m_frameBuffer, a std::deque
 *    capped at m_maxBufferSize (default: 900 frames = 30 s at 30 fps).
 *    This matches EegSyncManager's 30-second EEG buffer, ensuring both
 *    streams cover the same time window for bidirectional alignment.
 *    The buffer is sorted by lslTimestamp (insertion order from the camera).
 *
 *    getFrameAtTime(lslTimestamp) uses binary search (O(log N)) to return the
 *    frame closest to a given LSL time — the mirror of
 *    EegSyncManager::getEEGForFrame() but for the video side.
 *
 *    Together, these two APIs enable bidirectional alignment:
 *      • "Which EEG data matches this video frame?" → EegSyncManager
 *      • "Which video frame matches this EEG timestamp?" → VideoBackend
 *
 *  VIDEO SINK:
 *    The QML VideoOutput element sets its videoOutput.videoSink property.
 *    VideoBackend stores this sink and forwards new frames to it via
 *    updateVideoSink(QImage). However, in the typical path (capture session
 *    active), the QML VideoOutput is connected directly to the
 *    QMediaCaptureSession (via CameraManager::captureSession), which bypasses
 *    the per-frame QImage conversion entirely. The sink path is used when
 *    explicit frame manipulation is required.
 *
 *  DATA FLOW:
 *    CameraManager::frameReady(VideoFramePacket)     [per-frame, ~30 Hz]
 *      → VideoBackend::onFrameReady()
 *          addFrameToBuffer()    — stores to ring buffer
 *          updateVideoSink()     — pushes QImage to QML VideoOutput (if set)
 *          emit frameReceived()  — notifies QML of new timestamp
 *
 *  QML-SIDE EEG SYNCHRONIZATION (VideoDisplayWindow.qml):
 *    The frameReceived(lslTimestamp) signal is connected in QML to a handler
 *    that calls EegSyncManager.getEEGForFrame(lslTimestamp). This returns
 *    a QVariantMap with the matched EEG sample, sync offset, and out-of-range
 *    status, which drives the on-screen sync health overlays. This is the
 *    live, per-frame synchronization feedback loop for the operator.
 *
 *  THREADING:
 *    All slots run on the main thread. Qt::QueuedConnection is used for
 *    CameraManager::frameReady to ensure frame processing stays on the
 *    main thread even if CameraManager emits from a different thread.
 *    m_bufferMutex protects m_frameBuffer for safe access from getFrameAtTime()
 *    which may be called from QML on the render thread.
 *
 * ==========================================================================
 */

#ifndef VIDEOBACKEND_H
#define VIDEOBACKEND_H

#include <QObject>
#include <QImage>
#include <QVideoSink>
#include <QVideoFrame>
#include <QMutex>
#include <QVariant>
#include <deque>
#include <QtQml/qqmlregistration.h>
#include "cameramanager.h"
#include "videoframepacket.h"

class VideoBackend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    // --- Camera identification (set from QML to specify which camera to use) ---
    Q_PROPERTY(QString cameraId READ cameraId WRITE setCameraId NOTIFY cameraIdChanged FINAL)
    Q_PROPERTY(QString cameraName READ cameraName NOTIFY cameraIdChanged FINAL)

    // --- Video sink — receives decoded frames for display in VideoOutput ---
    Q_PROPERTY(QVideoSink* videoSink READ videoSink WRITE setVideoSink NOTIFY videoSinkChanged FINAL)

    // --- Capture state ---
    Q_PROPERTY(bool isCapturing READ isCapturing NOTIFY isCapturingChanged FINAL)
    Q_PROPERTY(bool isConnected READ isConnected NOTIFY isConnectedChanged FINAL)

    // --- Statistics ---
    Q_PROPERTY(double currentFps READ currentFps NOTIFY statsUpdated FINAL)
    Q_PROPERTY(qint64 frameCount READ frameCount NOTIFY statsUpdated FINAL)
    Q_PROPERTY(double lastFrameTimestamp READ lastFrameTimestamp NOTIFY frameReceived FINAL)
    Q_PROPERTY(int bufferSize READ bufferSize NOTIFY statsUpdated FINAL)

    // --- Buffer configuration ---
    Q_PROPERTY(int maxBufferSize READ maxBufferSize WRITE setMaxBufferSize NOTIFY maxBufferSizeChanged FINAL)

public:
    explicit VideoBackend(QObject* parent = nullptr);
    ~VideoBackend();

    // --- Camera identification ---

    QString cameraId() const { return m_cameraId; }

    /* Sets the camera by its platform device ID. Searches CameraManager's
     * device list for a matching entry and calls setCurrentCameraIndex()
     * only if the camera is actually different from the current one. */
    void setCameraId(const QString& id);

    QString cameraName() const;

    // --- Video sink ---

    QVideoSink* videoSink() const { return m_videoSink; }

    /* Stores the QVideoSink provided by the QML VideoOutput element.
     * Frames are pushed to this sink in updateVideoSink() when explicit
     * QImage-based delivery is needed. */
    void setVideoSink(QVideoSink* sink);

    // --- Capture control ---

    /* Clears the frame buffer, resets statistics, and calls
     * CameraManager::startCapture(). Sets isConnected=true immediately. */
    Q_INVOKABLE void startCapture();

    /* Calls CameraManager::stopCapture() and resets statistics. */
    Q_INVOKABLE void stopCapture();

    bool isCapturing() const { return m_isCapturing; }
    bool isConnected() const { return m_isConnected; }

    // --- Statistics ---

    double currentFps() const { return m_currentFps; }
    qint64 frameCount() const { return m_frameCount; }
    double lastFrameTimestamp() const { return m_lastFrameTimestamp; }
    int bufferSize() const;

    // --- Buffer configuration ---

    int maxBufferSize() const { return m_maxBufferSize; }

    /* Changes the ring buffer capacity and trims excess frames from the front. */
    void setMaxBufferSize(int size);

    // --- Synchronization API ---

    /* Returns the VideoFramePacket whose lslTimestamp is closest to the
     * requested LSL time. Uses binary search on the sorted frame buffer.
     * Returns an invalid (default-constructed) packet if the buffer is empty.
     * This is the video-side mirror of EegSyncManager::getEEGForFrame(). */
    Q_INVOKABLE VideoFramePacket getFrameAtTime(double lslTimestamp) const;

    /* Returns all LSL timestamps currently in the buffer as a QVariantList.
     * Intended for diagnostic display in the UI. */
    Q_INVOKABLE QVariantList getFrameTimestamps() const;

    Q_INVOKABLE double getLatestTimestamp() const;
    Q_INVOKABLE double getOldestTimestamp() const;

    /* Returns a snapshot copy of the full frame buffer.
     * Thread-safe (acquires m_bufferMutex). */
    std::deque<VideoFramePacket> frameBuffer() const;

    void clearBuffer();

signals:
    void cameraIdChanged();
    void videoSinkChanged();
    void isCapturingChanged();
    void isConnectedChanged();
    void statsUpdated();

    /* Emitted on every frame arrival; carries the LSL timestamp so that
     * EEG sync queries can be triggered immediately from QML. */
    void frameReceived(double lslTimestamp);

    void maxBufferSizeChanged();
    void errorOccurred(const QString& error);

private slots:
    /* Receives VideoFramePacket from CameraManager::frameReady().
     * Stores the frame, updates statistics, forwards to video sink,
     * and emits frameReceived(). */
    void onFrameReady(const VideoFramePacket& packet);

    void onCameraError(const QString& error);

private:
    /* Appends packet to m_frameBuffer and pops the oldest entry if
     * the buffer exceeds m_maxBufferSize. Thread-safe. */
    void addFrameToBuffer(const VideoFramePacket& packet);

    /* Wraps the QImage in a QVideoFrame and pushes it to m_videoSink.
     * No-op if sink is null or image is null. */
    void updateVideoSink(const QImage& image);

    CameraManager* m_cameraManager = nullptr;

    QString      m_cameraId;
    QVideoSink*  m_videoSink    = nullptr;

    bool   m_isCapturing = false;
    bool   m_isConnected = false;

    double  m_currentFps          = 0.0;
    qint64  m_frameCount          = 0;
    double  m_lastFrameTimestamp  = 0.0;

    mutable QMutex             m_bufferMutex;
    std::deque<VideoFramePacket> m_frameBuffer;

    // Buffer holds 30 seconds of frames at 30 fps = 900 entries.
    // This matches EegSyncManager's 30-second EEG buffer, ensuring that
    // both streams cover the same time window for bidirectional alignment:
    //   EEG → Video: EegSyncManager   (30 s of EEG samples)
    //   Video → EEG: VideoBackend     (30 s of video frames)
    // Mismatched buffer sizes would create a dead zone where one direction
    // of synchronization silently fails because the other buffer has already
    // evicted the matching data.
    int m_maxBufferSize = 900; // 30 s × 30 fps — matched to EEG buffer duration
};

#endif // VIDEOBACKEND_H
