/*
 * ==========================================================================
 *  cameramanager.cpp — Camera Device Manager Implementation
 * ==========================================================================
 *  See cameramanager.h for architecture overview, dual-sink model,
 *  LSL timestamping strategy, and format auto-selection heuristic.
 * ==========================================================================
 */

#include "cameramanager.h"

#include <QDebug>
#include <QTimer>
#include <QDateTime>
#include <QVideoFrame>

CameraManager* CameraManager::s_instance = nullptr;

CameraManager* CameraManager::instance()
{
    if (!s_instance)
        s_instance = new CameraManager();
    return s_instance;
}

CameraManager* CameraManager::create(QQmlEngine* qmlEngine, QJSEngine* jsEngine)
{
    Q_UNUSED(qmlEngine)
    Q_UNUSED(jsEngine)
    return instance();
}

CameraManager::CameraManager(QObject* parent)
    : QObject(parent)
{
    qInfo() << "[CameraManager] Initializing...";

    // Internal sink: receives frames when no external (QML) sink is attached.
    // The connection is permanent; onVideoFrameChanged() checks m_isCapturing
    // before acting so it is a no-op during preview-only mode.
    m_videoSink = new QVideoSink(this);
    connect(m_videoSink, &QVideoSink::videoFrameChanged,
            this, &CameraManager::onVideoFrameChanged);

    // The capture session acts as the switchboard: it holds the QCamera
    // source and routes decoded frames to whichever QVideoSink is active.
    m_captureSession = new QMediaCaptureSession(this);
    m_captureSession->setVideoSink(m_videoSink);

    m_fpsTimer = new QTimer(this);
    m_fpsTimer->setInterval(1000);
    connect(m_fpsTimer, &QTimer::timeout, this, &CameraManager::updateFpsCounter);

    // Retry timer: used when the camera driver reports a transient error
    // (common on laptops where the integrated camera may be briefly busy).
    m_startRetryTimer = new QTimer(this);
    m_startRetryTimer->setSingleShot(true);
    m_startRetryTimer->setInterval(500); // 500 ms between retries
    connect(m_startRetryTimer, &QTimer::timeout, this, [this]() {
        if (!m_camera) return;
        if (m_camera->isActive()) {
            qInfo() << "[CameraManager] Camera became active after retry — OK";
            m_startRetryCount = 0;
            return;
        }
        if (m_startRetryCount < k_maxStartRetries) {
            m_startRetryCount++;
            qWarning() << "[CameraManager] Camera not yet active — retry"
                       << m_startRetryCount << "/" << k_maxStartRetries;
            m_camera->start();
            m_startRetryTimer->start();
        } else {
            qWarning() << "[CameraManager] Camera failed to start after"
                       << k_maxStartRetries << "retries — trying fallback format";
            startCameraWithFallback();
        }
    });

    refreshCameraList();
}

CameraManager::~CameraManager()
{
    qInfo() << "CameraManager destroyed";
    stopCapture();
    cleanupCamera();

    if (s_instance == this)
        s_instance = nullptr;
}

// ============================================================================
// Camera Enumeration
// ============================================================================

void CameraManager::refreshCameraList()
{
    qInfo() << "[CameraManager] Refreshing camera list...";

    m_cameras.clear();

    const QList<QCameraDevice> devices = QMediaDevices::videoInputs();
    const QCameraDevice defaultDevice  = QMediaDevices::defaultVideoInput();

    if (devices.isEmpty()) {
        qWarning() << "[CameraManager] No video input devices found on this system!";
        emit availableCamerasChanged();
        return;
    }

    qInfo() << "[CameraManager] Found" << devices.size() << "camera device(s):";

    for (const QCameraDevice& device : devices)
    {
        CameraInfo info;
        info.id          = device.id();
        info.description = device.description();
        info.isDefault   = (device == defaultDevice);

        for (const QCameraFormat& format : device.videoFormats())
        {
            CameraFormat fmt;
            fmt.width        = format.resolution().width();
            fmt.height       = format.resolution().height();
            fmt.minFrameRate = format.minFrameRate();
            fmt.maxFrameRate = format.maxFrameRate();
            info.formats.append(fmt);
        }

        m_cameras.append(info);
        qInfo() << "  [" << (info.isDefault ? "DEFAULT" : "      ") << "]"
                << info.description
                << "— id:" << QString::fromLatin1(info.id.toHex())
                << "—" << info.formats.size() << "format(s)";

        // Log the first few formats so we can diagnose resolution/FPS issues
        for (int i = 0; i < qMin(5, info.formats.size()); ++i) {
            const CameraFormat& f = info.formats[i];
            qInfo() << "      format" << i << ":"
                    << f.width << "x" << f.height
                    << "@" << f.minFrameRate << "-" << f.maxFrameRate << "fps";
        }
        if (info.formats.size() > 5)
            qInfo() << "      ... +" << (info.formats.size() - 5) << "more formats";
    }

    emit availableCamerasChanged();

    // Auto-select the system default camera on first enumeration
    if (m_currentCameraIndex < 0 && !m_cameras.isEmpty())
    {
        for (int i = 0; i < m_cameras.size(); ++i)
        {
            if (m_cameras[i].isDefault)
            {
                qInfo() << "[CameraManager] Auto-selecting default camera at index" << i;
                setCurrentCameraIndex(i);
                return;
            }
        }
        qInfo() << "[CameraManager] No default camera found — auto-selecting index 0";
        setCurrentCameraIndex(0);
    }
}

void CameraManager::logCameraDevices() const
{
    // Separate diagnostic dump callable at any time (e.g. after a camera error)
    const QList<QCameraDevice> devices = QMediaDevices::videoInputs();
    qInfo() << "[CameraManager] === Camera Diagnostic Dump ===";
    qInfo() << "[CameraManager] Total devices visible to OS:" << devices.size();
    for (int i = 0; i < devices.size(); ++i) {
        const QCameraDevice& d = devices[i];
        qInfo() << "  Device" << i << ":" << d.description()
                << "| default:" << (d == QMediaDevices::defaultVideoInput())
                << "| formats:" << d.videoFormats().size();
    }
    if (m_camera) {
        qInfo() << "[CameraManager] Current QCamera object active:" << m_camera->isActive()
                << "| error:" << m_camera->errorString();
    } else {
        qInfo() << "[CameraManager] No QCamera object instantiated";
    }
    qInfo() << "[CameraManager] === End Diagnostic Dump ===";
}

QVariantList CameraManager::availableCameras() const
{
    QVariantList result;
    for (const CameraInfo& info : m_cameras)
    {
        QVariantMap map;
        map["id"]          = info.id;
        map["description"] = info.description;
        map["isDefault"]   = info.isDefault;
        map["formatCount"] = info.formats.size();
        result.append(map);
    }
    return result;
}

// ============================================================================
// Camera Selection
// ============================================================================

void CameraManager::setCurrentCameraIndex(int index)
{
    if (index == m_currentCameraIndex)
        return;

    if (index < -1 || index >= m_cameras.size())
    {
        qWarning() << "CameraManager: Invalid camera index:" << index;
        return;
    }

    // Preserve operational state so we can restore it after switching hardware
    bool wasCapturing    = m_isCapturing;
    bool wasPreviewActive = m_isPreviewActive;

    if (m_isCapturing)    stopCapture();
    if (m_isPreviewActive) stopPreview();

    m_currentCameraIndex = index;
    m_currentFormatIndex = -1;

    qInfo() << "CameraManager: Selected camera index:" << index;

    if (index >= 0)
    {
        const QList<QCameraDevice> devices = QMediaDevices::videoInputs();
        for (const QCameraDevice& device : devices)
        {
            if (device.id() == m_cameras[index].id)
            {
                setupCamera(device);
                break;
            }
        }

        populateFormatsForCurrentCamera();

        // Auto-select best format using the scoring heuristic (see header):
        // prefer 1080p at 30-60 fps; fall back to highest resolution.
        if (!m_cameras[index].formats.isEmpty())
        {
            int bestIndex = 0;
            int bestScore = 0;

            for (int i = 0; i < m_cameras[index].formats.size(); ++i)
            {
                const CameraFormat& fmt = m_cameras[index].formats[i];
                int score = fmt.width * fmt.height;

                if (fmt.maxFrameRate >= 30 && fmt.maxFrameRate <= 60)
                    score += 1000000;

                if (fmt.height == 1080)
                    score += 500000;

                if (score > bestScore)
                {
                    bestScore = score;
                    bestIndex = i;
                }
            }

            setCurrentFormatIndex(bestIndex);
        }
    }

    emit currentCameraIndexChanged();
    emit availableFormatsChanged();

    // Restore previous operational state with the new camera
    if (wasPreviewActive && index >= 0) startPreview();
    if (wasCapturing     && index >= 0) startCapture();
}

QString CameraManager::currentCameraName() const
{
    if (m_currentCameraIndex >= 0 && m_currentCameraIndex < m_cameras.size())
        return m_cameras[m_currentCameraIndex].description;
    return QString();
}

// ============================================================================
// Format Selection
// ============================================================================

QVariantList CameraManager::availableFormats() const
{
    QVariantList result;

    if (m_currentCameraIndex >= 0 && m_currentCameraIndex < m_cameras.size())
    {
        const QList<CameraFormat>& formats = m_cameras[m_currentCameraIndex].formats;
        for (int i = 0; i < formats.size(); ++i)
        {
            QVariantMap map;
            map["index"]         = i;
            map["width"]         = formats[i].width;
            map["height"]        = formats[i].height;
            map["minFps"]        = formats[i].minFrameRate;
            map["maxFps"]        = formats[i].maxFrameRate;
            map["displayString"] = formats[i].toString();
            map["resolution"]    = formats[i].resolutionString();
            result.append(map);
        }
    }

    return result;
}

void CameraManager::setCurrentFormatIndex(int index)
{
    if (index == m_currentFormatIndex)
        return;

    if (m_currentCameraIndex < 0 || m_currentCameraIndex >= m_cameras.size())
        return;

    const QList<CameraFormat>& formats = m_cameras[m_currentCameraIndex].formats;
    if (index < -1 || index >= formats.size())
    {
        qWarning() << "CameraManager: Invalid format index:" << index;
        return;
    }

    m_currentFormatIndex = index;
    qInfo() << "CameraManager: Selected format index:" << index;

    // Locate the matching QCameraFormat by resolution and FPS, then apply it.
    // We re-query QMediaDevices to get the live QCameraFormat object because
    // our CameraFormat struct is a value copy that does not hold a Qt handle.
    if (m_camera && index >= 0)
    {
        const CameraFormat& fmt = formats[index];
        const QList<QCameraDevice> devices = QMediaDevices::videoInputs();

        for (const QCameraDevice& device : devices)
        {
            if (device.id() != m_cameras[m_currentCameraIndex].id)
                continue;

            for (const QCameraFormat& qfmt : device.videoFormats())
            {
                if (qfmt.resolution().width()  == fmt.width  &&
                    qfmt.resolution().height() == fmt.height &&
                    qFuzzyCompare(static_cast<float>(qfmt.maxFrameRate()),
                                  static_cast<float>(fmt.maxFrameRate)))
                {
                    m_camera->setCameraFormat(qfmt);
                    qInfo() << "CameraManager: Applied format:" << fmt.toString();
                    break;
                }
            }
            break;
        }
    }

    emit currentFormatIndexChanged();
}

QString CameraManager::currentFormatString() const
{
    if (m_currentCameraIndex >= 0 && m_currentCameraIndex < m_cameras.size() &&
        m_currentFormatIndex  >= 0 && m_currentFormatIndex  < m_cameras[m_currentCameraIndex].formats.size())
    {
        return m_cameras[m_currentCameraIndex].formats[m_currentFormatIndex].toString();
    }
    return QString();
}

// ============================================================================
// Camera Lifecycle (private helpers)
// ============================================================================

void CameraManager::setupCamera(const QCameraDevice& device)
{
    cleanupCamera();

    m_startRetryCount = 0;
    if (m_startRetryTimer)
        m_startRetryTimer->stop();

    m_camera = new QCamera(device, this);
    connect(m_camera, &QCamera::errorOccurred,  this, &CameraManager::onCameraErrorOccurred);
    connect(m_camera, &QCamera::activeChanged,  this, &CameraManager::onCameraActiveChanged);

    m_captureSession->setCamera(m_camera);

    qInfo() << "[CameraManager] Camera object created for:" << device.description();
}

void CameraManager::startCameraWithFallback()
{
    if (!m_camera || m_currentCameraIndex < 0)
        return;

    const QList<CameraFormat>& formats = m_cameras[m_currentCameraIndex].formats;

    // Walk from index 0 (lowest res) upward trying each format until one works.
    // Laptop integrated cameras often refuse high-resolution modes at startup
    // and need a lower-res format to initialise correctly first.
    qWarning() << "[CameraManager] Trying fallback format selection for"
               << m_cameras[m_currentCameraIndex].description;

    const QList<QCameraDevice> devices = QMediaDevices::videoInputs();
    for (const QCameraDevice& device : devices)
    {
        if (device.id() != m_cameras[m_currentCameraIndex].id)
            continue;

        // Find the smallest valid format (non-zero resolution, any frame rate)
        // as the guaranteed-to-work fallback.
        for (const QCameraFormat& qfmt : device.videoFormats())
        {
            if (qfmt.resolution().width() <= 0 || qfmt.resolution().height() <= 0)
                continue;

            qInfo() << "[CameraManager] Fallback: trying"
                    << qfmt.resolution().width() << "x" << qfmt.resolution().height()
                    << "@" << qfmt.maxFrameRate() << "fps";

            m_camera->setCameraFormat(qfmt);

            // Update our index to match the fallback format
            for (int i = 0; i < formats.size(); ++i) {
                if (formats[i].width  == qfmt.resolution().width() &&
                    formats[i].height == qfmt.resolution().height())
                {
                    m_currentFormatIndex = i;
                    emit currentFormatIndexChanged();
                    break;
                }
            }

            m_camera->start();

            // Give the camera driver 800 ms to respond before accepting failure.
            // Checking isActive() synchronously after start() is unreliable on
            // some integrated camera drivers — they report active asynchronously.
            qInfo() << "[CameraManager] Fallback format applied — waiting for activation";
            return;
        }
        break;
    }

    qWarning() << "[CameraManager] All fallback formats exhausted — camera may not work";
    logCameraDevices();
    emit errorOccurred("Camera failed to start. Please check camera permissions "
                       "and ensure no other application is using the camera.");
}

void CameraManager::cleanupCamera()
{
    if (m_camera)
    {
        m_camera->stop();
        m_captureSession->setCamera(nullptr);
        delete m_camera;
        m_camera = nullptr;
    }
}

void CameraManager::populateFormatsForCurrentCamera()
{
    // Formats are already populated in refreshCameraList().
    // Emitting the signal is enough to refresh any bound QML ComboBox.
    emit availableFormatsChanged();
}

// ============================================================================
// Capture Control
// ============================================================================

void CameraManager::startCapture()
{
    if (m_isCapturing)
    {
        qWarning() << "CameraManager: Already capturing";
        return;
    }

    if (!m_camera)
    {
        qWarning() << "CameraManager: No camera selected";
        emit errorOccurred("No camera selected");
        return;
    }

    qInfo() << "CameraManager: Starting capture...";

    // Transition cleanly from preview mode (camera may already be running)
    if (m_isPreviewActive)
    {
        m_isPreviewActive = false;
        emit isPreviewActiveChanged();
    }

    // Route frames through the external sink if one is registered (QML VideoOutput).
    // This is the preferred path: the hardware decoder feeds one sink that serves
    // both display and the timestamp callback — no double decode needed.
    if (m_externalSink)
    {
        m_captureSession->setVideoSink(m_externalSink.data());

        // Re-connect the callback to the external sink (disconnect first to
        // avoid double-firing if setExternalVideoSink() was called earlier).
        disconnect(m_externalSink, &QVideoSink::videoFrameChanged,
                   this, &CameraManager::onVideoFrameChanged);
        connect(m_externalSink, &QVideoSink::videoFrameChanged,
                this, &CameraManager::onVideoFrameChanged);
    }
    else
    {
        m_captureSession->setVideoSink(m_videoSink.data());
    }

    m_frameCount         = 0;
    m_framesAtLastUpdate = 0;
    m_lastFpsUpdateTime  = QDateTime::currentMSecsSinceEpoch();

    // Always call start() — even if isActive() returns true.
    // Some integrated camera drivers report active=false until the first
    // frame arrives, so guarding on isActive() here would leave the camera
    // silent. start() is idempotent when the camera is already running.
    m_startRetryCount = 0;
    m_camera->start();

    // If the camera is not active after the call (async driver), schedule a
    // retry so we don't silently leave the user with no video on laptops.
    if (!m_camera->isActive()) {
        qInfo() << "[CameraManager] Camera not immediately active after start() — "
                   "scheduling retry checks (async driver)";
        m_startRetryTimer->start();
    } else {
        qInfo() << "[CameraManager] Camera active immediately after start()";
    }

    m_isCapturing = true;
    m_fpsTimer->start();

    emit isCapturingChanged();
}

void CameraManager::stopCapture()
{
    if (!m_isCapturing)
        return;

    qInfo() << "CameraManager: Stopping capture...";

    m_fpsTimer->stop();

    if (m_camera)
        m_camera->stop();

    m_isCapturing = false;
    m_currentFps  = 0.0;

    emit isCapturingChanged();
    emit fpsUpdated();
}

// ============================================================================
// Preview Control
// ============================================================================

void CameraManager::startPreview()
{
    if (m_isPreviewActive)
        return;

    if (!m_camera)
    {
        qWarning() << "[CameraManager] No camera selected for preview";
        return;
    }

    qInfo() << "[CameraManager] Starting preview for:"
            << (m_currentCameraIndex >= 0 ? m_cameras[m_currentCameraIndex].description : "unknown");

    m_startRetryCount = 0;
    m_camera->start();

    if (!m_camera->isActive()) {
        qInfo() << "[CameraManager] Preview camera not yet active — scheduling retry";
        m_startRetryTimer->start();
    }

    m_isPreviewActive = true;

    emit isPreviewActiveChanged();
}

void CameraManager::stopPreview()
{
    if (!m_isPreviewActive)
        return;

    qInfo() << "CameraManager: Stopping preview...";

    if (m_externalSink)
    {
        m_externalSink = nullptr;
        if (m_captureSession)
            m_captureSession->setVideoSink(m_videoSink.data());
    }

    if (!m_isCapturing && m_camera)
        m_camera->stop();

    m_isPreviewActive = false;

    emit isPreviewActiveChanged();
}

// ============================================================================
// Video Sink Management
// ============================================================================

void CameraManager::setExternalVideoSink(QVideoSink* sink)
{
    if (m_externalSink)
    {
        disconnect(m_externalSink, &QVideoSink::videoFrameChanged,
                   this, &CameraManager::onVideoFrameChanged);
    }

    m_externalSink = sink;

    if (m_captureSession)
        m_captureSession->setVideoSink(sink ? sink : m_videoSink.data());

    // In capture mode, also hook the frame callback to the new external sink
    if (sink && m_isCapturing)
    {
        connect(sink, &QVideoSink::videoFrameChanged,
                this, &CameraManager::onVideoFrameChanged);
    }
}

// ============================================================================
// Frame Hot Path
// ============================================================================

void CameraManager::onVideoFrameChanged(const QVideoFrame& frame)
{
    if (!frame.isValid())
        return;

    // Stamp the LSL timestamp as early as possible — before any processing.
    // This minimizes the jitter between the physical moment of capture and
    // the recorded timestamp. Any delay after this line adds to sync error.
    //
    // This timestamp flows through the entire synchronization pipeline:
    //   1. VideoBackend stores it in the frame ring buffer
    //   2. VideoDisplayWindow.qml receives it via frameReceived(lslTimestamp)
    //   3. QML calls EegSyncManager.getEEGForFrame(lslTimestamp)
    //   4. EegSyncManager applies time_correction(), searches EEG buffer,
    //      validates timestamp range, and returns matched EEG data + offsetMs
    //   5. QML updates the sync health overlay with the result
    //
    // The timestamp is also forwarded to RecordingManager for the frames CSV,
    // enabling post-hoc synchronization in offline analysis tools.
    double lslTimestamp = lsl::local_clock();

    m_frameCount++;

    if (m_isCapturing)
    {
        m_lastFrameTimestamp = lslTimestamp;
        emit frameTimestampUpdated();

        // Emit a lightweight packet (no QImage conversion).
        // The QML VideoOutput already displays the frame via the capture
        // session; we only need the timestamp for EEG sync and recording.
        emit frameReady(VideoFramePacket(QImage(), lslTimestamp, m_frameCount));
    }
}

QImage CameraManager::videoFrameToImage(const QVideoFrame& frame)
{
    // Used only for still capture or when pixel data is explicitly needed.
    // Not called on the normal frame hot path.
    QVideoFrame frameCopy = frame;

    if (!frameCopy.map(QVideoFrame::ReadOnly))
    {
        qWarning() << "CameraManager: Failed to map video frame";
        return QImage();
    }

    QImage image = frameCopy.toImage();
    frameCopy.unmap();

    if (image.isNull())
    {
        qWarning() << "CameraManager: Failed to convert frame to image";
        return QImage();
    }

    if (image.format() != QImage::Format_RGB32 &&
        image.format() != QImage::Format_ARGB32)
    {
        image = image.convertToFormat(QImage::Format_RGB32);
    }

    return image;
}

// ============================================================================
// Event Handlers
// ============================================================================

void CameraManager::onCameraErrorOccurred(QCamera::Error error, const QString& errorString)
{
    qWarning() << "[CameraManager] Camera error" << static_cast<int>(error) << ":" << errorString;

    // Dump full diagnostic info so the developer can see what happened
    logCameraDevices();

    // On a transient "access denied" or "device busy" error, the retry timer
    // will automatically attempt to restart the camera. For other errors,
    // propagate to the UI so the user knows.
    if (error != QCamera::Error::NoError) {
        emit errorOccurred(QString("Camera error: %1").arg(errorString));
    }
}

void CameraManager::onCameraActiveChanged(bool active)
{
    qInfo() << "[CameraManager] Camera active changed:" << active;

    if (active) {
        // Camera successfully started — cancel any pending retry
        m_startRetryCount = 0;
        if (m_startRetryTimer)
            m_startRetryTimer->stop();

        qInfo() << "[CameraManager] Camera is now active and delivering frames";
    } else if (m_isCapturing) {
        // Camera became inactive unexpectedly during capture — propagate
        qWarning() << "[CameraManager] Camera became inactive while capturing!";
        m_isCapturing = false;
        emit isCapturingChanged();
    }
}

void CameraManager::updateFpsCounter()
{
    qint64 now     = QDateTime::currentMSecsSinceEpoch();
    qint64 elapsed = now - m_lastFpsUpdateTime;

    if (elapsed > 0)
    {
        qint64 framesDelta = m_frameCount - m_framesAtLastUpdate;
        m_currentFps = (framesDelta * 1000.0) / elapsed;
    }

    m_lastFpsUpdateTime  = now;
    m_framesAtLastUpdate = m_frameCount;

    emit fpsUpdated();
}
