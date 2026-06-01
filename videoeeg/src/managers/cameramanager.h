/*
 * ==========================================================================
 *  cameramanager.h — Camera Device Manager with LSL Frame Timestamping
 * ==========================================================================
 *
 *  PURPOSE:
 *    Central manager for all camera hardware interaction: device enumeration,
 *    format selection, preview (settings window), and frame capture with
 *    LSL-synchronized timestamps. It decouples the hardware-specific Qt
 *    Multimedia layer from the rest of the application.
 *
 *  DESIGN PATTERNS:
 *    Singleton (QML_SINGLETON) — one camera is active at a time and its
 *    state must be accessible from both the settings window (preview) and
 *    the recording window (capture) simultaneously.
 *    Bridge — translates Qt Multimedia's QCameraDevice / QCameraFormat types
 *    into application-level CameraInfo / CameraFormat structs that are
 *    decoupled from the Qt multimedia layer internals.
 *
 *  LSL TIMESTAMPING STRATEGY:
 *    The key synchronization insight: lsl::local_clock() is called inside
 *    onVideoFrameChanged() before any other processing. This gives the
 *    earliest possible timestamp for each frame — before image conversion,
 *    before signal dispatch, before any Qt event queue latency. The
 *    resulting timestamp is passed to EegSyncManager::getEEGForFrame()
 *    which looks up the EEG samples that were recorded at that exact moment.
 *
 *  DUAL-SINK ARCHITECTURE:
 *    Qt Multimedia requires a QMediaCaptureSession to hold both the
 *    QCamera and one active QVideoSink at a time. Two operational modes:
 *
 *    Preview mode (settings window open):
 *      m_captureSession → m_videoSink (internal)
 *      The external QML VideoOutput's sink is set via setExternalVideoSink()
 *      to show the live feed in the settings dialog.
 *
 *    Capture mode (recording in progress):
 *      If m_externalSink is set: m_captureSession → m_externalSink
 *        The external sink drives both the QML VideoOutput display AND
 *        the frame callback (connected to onVideoFrameChanged).
 *      If no external sink: m_captureSession → m_videoSink (internal)
 *
 *    This design avoids double-decoding the video stream: the hardware
 *    decoder feeds one path, and display + timestamping share that path.
 *
 *  FORMAT AUTO-SELECTION HEURISTIC:
 *    When a camera is selected, setCurrentCameraIndex() scores all formats:
 *      base score   = width × height (prefer higher resolution)
 *      +1,000,000   if 30 ≤ maxFPS ≤ 60 (prefer standard frame rates)
 *      +500,000     if height == 1080    (prefer full-HD)
 *    The highest-scoring format is selected automatically. This matches
 *    clinical video-EEG requirements (full-HD at 30 fps is the standard).
 *
 *  DATA FLOW:
 *    QMediaDevices::videoInputs()    [enumeration]
 *      → refreshCameraList()
 *    QCamera::start()                [hardware activation]
 *      → QVideoSink::videoFrameChanged(QVideoFrame)
 *        → onVideoFrameChanged()
 *            lsl::local_clock()      [timestamp acquisition]
 *            emit frameReady(VideoFramePacket)
 *              → VideoBackend::onFrameReady()
 *              → RecordingManager (via VideoBackend, for MKV recording)
 *
 * ==========================================================================
 */

#ifndef CAMERAMANAGER_H
#define CAMERAMANAGER_H

#include <QObject>
#include <QCamera>
#include <QMediaCaptureSession>
#include <QVideoSink>
#include <QVideoFrame>
#include <QMediaDevices>
#include <QCameraDevice>
#include <QCameraFormat>
#include <QPointer>
#include <QTimer>
#include <QVariant>
#include <QQmlEngine>
#include <QtQml/qqmlregistration.h>
#include <lsl_cpp.h>

#include "videoframepacket.h"

class CameraManager : public QObject
{
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

    // --- Camera enumeration ---
    Q_PROPERTY(QVariantList availableCameras READ availableCameras NOTIFY availableCamerasChanged FINAL)
    Q_PROPERTY(int currentCameraIndex READ currentCameraIndex WRITE setCurrentCameraIndex NOTIFY currentCameraIndexChanged FINAL)
    Q_PROPERTY(QString currentCameraName READ currentCameraName NOTIFY currentCameraIndexChanged FINAL)

    // --- Format selection ---
    Q_PROPERTY(QVariantList availableFormats READ availableFormats NOTIFY availableFormatsChanged FINAL)
    Q_PROPERTY(int currentFormatIndex READ currentFormatIndex WRITE setCurrentFormatIndex NOTIFY currentFormatIndexChanged FINAL)
    Q_PROPERTY(QString currentFormatString READ currentFormatString NOTIFY currentFormatIndexChanged FINAL)

    // --- Operational state ---
    Q_PROPERTY(bool isCapturing READ isCapturing NOTIFY isCapturingChanged FINAL)
    Q_PROPERTY(bool isPreviewActive READ isPreviewActive NOTIFY isPreviewActiveChanged FINAL)

    // --- Statistics ---
    Q_PROPERTY(double currentFps READ currentFps NOTIFY fpsUpdated FINAL)
    Q_PROPERTY(double lastFrameTimestamp READ lastFrameTimestamp NOTIFY frameTimestampUpdated FINAL)

    // --- Capture session (exposed for QML VideoOutput binding in preview) ---
    Q_PROPERTY(QMediaCaptureSession* captureSession READ captureSession CONSTANT FINAL)

public:
    static CameraManager* instance();
    static CameraManager* create(QQmlEngine* qmlEngine, QJSEngine* jsEngine);

    explicit CameraManager(QObject* parent = nullptr);
    ~CameraManager();

    // -----------------------------------------------------------------------
    // Camera enumeration
    // -----------------------------------------------------------------------

    /* Re-queries QMediaDevices::videoInputs() and rebuilds the device list.
     * Called once at construction and on-demand from the settings window.
     * Auto-selects the system default camera if none was previously selected. */
    Q_INVOKABLE void refreshCameraList();

    QVariantList availableCameras() const;
    QList<CameraInfo> cameraInfoList() const { return m_cameras; }

    // -----------------------------------------------------------------------
    // Camera selection
    // -----------------------------------------------------------------------

    int currentCameraIndex() const { return m_currentCameraIndex; }

    /* Switches the active camera. Stops any ongoing capture/preview first,
     * sets up the new QCamera object, auto-selects the best format using
     * the scoring heuristic (see header overview), then restores state.
     * @param index  Index into m_cameras (-1 = no camera) */
    Q_INVOKABLE void setCurrentCameraIndex(int index);

    QString currentCameraName() const;

    // -----------------------------------------------------------------------
    // Format selection
    // -----------------------------------------------------------------------

    QVariantList availableFormats() const;
    int currentFormatIndex() const { return m_currentFormatIndex; }

    /* Applies a specific format from the current camera's format list.
     * Looks up the matching QCameraFormat from QMediaDevices (by resolution
     * and FPS) and calls QCamera::setCameraFormat(). */
    Q_INVOKABLE void setCurrentFormatIndex(int index);

    QString currentFormatString() const;

    // -----------------------------------------------------------------------
    // Capture control
    // -----------------------------------------------------------------------

    /* Starts frame acquisition and LSL timestamping. If a preview was active,
     * transitions gracefully without restarting the hardware camera.
     * Activates the FPS monitoring timer. */
    Q_INVOKABLE void startCapture();

    /* Stops acquisition and FPS monitoring. Does not affect preview state. */
    Q_INVOKABLE void stopCapture();

    bool isCapturing() const { return m_isCapturing; }

    // -----------------------------------------------------------------------
    // Preview control (for the settings / configuration window)
    // -----------------------------------------------------------------------

    /* Starts the camera in preview-only mode: the live feed is shown in the
     * settings window via the external sink, but frameReady is not emitted
     * and no LSL timestamps are generated. */
    Q_INVOKABLE void startPreview();

    /* Stops preview mode. Clears the external sink reference and stops the
     * camera hardware if capture is also not active. */
    Q_INVOKABLE void stopPreview();

    bool isPreviewActive() const { return m_isPreviewActive; }

    // -----------------------------------------------------------------------
    // Video sink management
    // -----------------------------------------------------------------------

    /* Returns the internal QVideoSink (used as fallback when no external
     * sink is set). Not typically used directly from QML. */
    Q_INVOKABLE QVideoSink* videoSink() const { return m_videoSink; }

    /* Sets an external QVideoSink (obtained from a QML VideoOutput element)
     * to route the live camera feed for display. In capture mode, also
     * connects the frame callback to this sink to capture timestamps. */
    Q_INVOKABLE void setExternalVideoSink(QVideoSink* sink);

    /* Provides the QMediaCaptureSession to QML for VideoOutput source binding.
     * The QML VideoOutput uses captureSession as its source property to
     * display the camera feed without intermediate QImage conversion. */
    QMediaCaptureSession* captureSession() const { return m_captureSession.data(); }

    // -----------------------------------------------------------------------
    // Statistics
    // -----------------------------------------------------------------------

    double currentFps() const { return m_currentFps; }
    qint64 frameCount() const { return m_frameCount; }

    /* LSL timestamp of the most recently received frame. Connected to QML
     * via the frameTimestampUpdated() signal so the display can update. */
    double lastFrameTimestamp() const { return m_lastFrameTimestamp; }

signals:
    void availableCamerasChanged();
    void currentCameraIndexChanged();
    void availableFormatsChanged();
    void currentFormatIndexChanged();
    void isCapturingChanged();
    void isPreviewActiveChanged();

    /* Emitted once per second with the recalculated frames-per-second value. */
    void fpsUpdated();

    /* Emitted on every frame during capture mode. Carries no arguments
     * (by design) — QML reads lastFrameTimestamp() via the getter to
     * avoid per-frame QVariant allocation in the signal dispatch path. */
    void frameTimestampUpdated();

    /* Primary frame delivery signal. Carries a VideoFramePacket with the
     * LSL timestamp and (optionally) the pixel data. Connected to
     * VideoBackend::onFrameReady() and RecordingManager (for MKV). */
    void frameReady(const VideoFramePacket& packet);

    void errorOccurred(const QString& error);

private slots:
    /* THE FRAME HOT PATH — called by QVideoSink on every decoded frame.
     * Stamps the LSL timestamp immediately, increments counter, and emits
     * frameReady() if in capture mode. videoFrameToImage() is NOT called
     * here; QML VideoOutput handles display directly via the capture session. */
    void onVideoFrameChanged(const QVideoFrame& frame);

    void onCameraErrorOccurred(QCamera::Error error, const QString& errorString);
    void onCameraActiveChanged(bool active);

    /* Recalculates m_currentFps from frame count delta over the last second.
     * Triggered by m_fpsTimer at 1 Hz. */
    void updateFpsCounter();

private:
    /* Creates a new QCamera for the given device, wires error/active signals,
     * and attaches it to m_captureSession. Called by setCurrentCameraIndex(). */
    void setupCamera(const QCameraDevice& device);

    /* Stops and deletes the current QCamera. Detaches from m_captureSession.
     * Safe to call even if m_camera is null. */
    void cleanupCamera();

    void populateFormatsForCurrentCamera();

    /* Converts a QVideoFrame to a QImage in RGB32 format. Used only when a
     * pixel-accurate copy is needed (e.g. still capture). Not used on the
     * normal frame hot path. */
    QImage videoFrameToImage(const QVideoFrame& frame);

    /* Logs all detected cameras and their formats to the console.
     * Called from refreshCameraList() for startup diagnostics. */
    void logCameraDevices() const;

    /* Attempts to start the camera, trying progressively lower-resolution
     * formats if the preferred format is rejected by the driver.
     * Used for integrated laptop cameras that may refuse certain formats. */
    void startCameraWithFallback();

    static CameraManager* s_instance;

    QList<CameraInfo> m_cameras;
    int m_currentCameraIndex = -1;
    int m_currentFormatIndex = -1;

    QPointer<QCamera>               m_camera;
    QPointer<QMediaCaptureSession>  m_captureSession;
    QPointer<QVideoSink>            m_videoSink;     // Internal sink (fallback)
    QPointer<QVideoSink>            m_externalSink;  // QML VideoOutput sink

    bool m_isCapturing    = false;
    bool m_isPreviewActive = false;

    // Retry state for cameras that start asynchronously (common on laptops)
    int     m_startRetryCount  = 0;
    static constexpr int k_maxStartRetries = 3;
    QTimer* m_startRetryTimer  = nullptr;

    qint64 m_frameCount         = 0;
    double m_currentFps         = 0.0;
    double m_lastFrameTimestamp = 0.0;
    qint64 m_lastFpsUpdateTime  = 0;    // ms since epoch at last FPS calc
    qint64 m_framesAtLastUpdate = 0;    // frame count at last FPS calc
    QTimer* m_fpsTimer          = nullptr;
};

#endif // CAMERAMANAGER_H
