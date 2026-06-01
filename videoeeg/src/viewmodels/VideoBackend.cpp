/*
 * ==========================================================================
 *  VideoBackend.cpp — Video Display ViewModel Implementation
 * ==========================================================================
 *  See VideoBackend.h for architecture overview, data flow, and threading model.
 * ==========================================================================
 */

#include "VideoBackend.h"

#include <QDebug>
#include <QMutexLocker>
#include <QVariant>
#include <algorithm>
#include <cmath>

VideoBackend::VideoBackend(QObject* parent)
    : QObject(parent)
    , m_cameraManager(CameraManager::instance())
{
    qInfo() << "VideoBackend created";

    if (m_cameraManager)
    {
        // QueuedConnection for frameReady: CameraManager may emit from the
        // video sink callback thread; processing must happen on the main thread.
        connect(m_cameraManager, &CameraManager::frameReady,
                this, &VideoBackend::onFrameReady, Qt::QueuedConnection);

        connect(m_cameraManager, &CameraManager::errorOccurred,
                this, &VideoBackend::onCameraError);

        // Mirror CameraManager's FPS counter into our own stats property
        connect(m_cameraManager, &CameraManager::fpsUpdated,
                this, [this]() {
                    m_currentFps = m_cameraManager->currentFps();
                    emit statsUpdated();
                });

        // Mirror CameraManager's capture state so QML sees a consistent value
        connect(m_cameraManager, &CameraManager::isCapturingChanged,
                this, [this]() {
                    bool capturing = m_cameraManager->isCapturing();
                    if (m_isCapturing != capturing) {
                        m_isCapturing = capturing;
                        emit isCapturingChanged();
                    }
                });
    }
}

VideoBackend::~VideoBackend()
{
    qInfo() << "VideoBackend destroyed";
    stopCapture();
}

void VideoBackend::setCameraId(const QString& id)
{
    if (m_cameraId == id) {
        return;
    }

    m_cameraId = id;
    qInfo() << "VideoBackend: Camera ID set to:" << id;

    // Find camera by ID - only set index if different camera
    if (m_cameraManager && !id.isEmpty()) {
        QVariantList cameras = m_cameraManager->availableCameras();
        for (int i = 0; i < cameras.size(); ++i) {
            if (cameras[i].toMap()["id"].toString() == id) {
                // Only change camera if it's a different one
                if (m_cameraManager->currentCameraIndex() != i) {
                    m_cameraManager->setCurrentCameraIndex(i);
                }
                break;
            }
        }
    }

    emit cameraIdChanged();
}

QString VideoBackend::cameraName() const
{
    if (m_cameraManager) {
        return m_cameraManager->currentCameraName();
    }
    return QString();
}

void VideoBackend::setVideoSink(QVideoSink* sink)
{
    if (m_videoSink == sink) {
        return;
    }

    m_videoSink = sink;
    qInfo() << "VideoBackend: Video sink set:" << sink;

    emit videoSinkChanged();
}

void VideoBackend::startCapture()
{
    if (m_isCapturing) {
        qWarning() << "VideoBackend: Already capturing";
        return;
    }

    if (!m_cameraManager) {
        emit errorOccurred("Camera manager not available");
        return;
    }

    qInfo() << "VideoBackend: Starting capture...";

    // Clear buffer before starting
    clearBuffer();
    m_frameCount = 0;
    m_lastFrameTimestamp = 0.0;

    m_cameraManager->startCapture();

    m_isCapturing = true;
    m_isConnected = true;

    emit isCapturingChanged();
    emit isConnectedChanged();
}

void VideoBackend::stopCapture()
{
    if (!m_isCapturing) {
        return;
    }

    qInfo() << "VideoBackend: Stopping capture...";

    if (m_cameraManager) {
        m_cameraManager->stopCapture();
    }

    m_isCapturing = false;
    m_isConnected = false;
    m_currentFps = 0.0;

    emit isCapturingChanged();
    emit isConnectedChanged();
    emit statsUpdated();
}

int VideoBackend::bufferSize() const
{
    QMutexLocker locker(&m_bufferMutex);
    return static_cast<int>(m_frameBuffer.size());
}

void VideoBackend::setMaxBufferSize(int size)
{
    if (size == m_maxBufferSize || size < 1) {
        return;
    }

    m_maxBufferSize = size;
    emit maxBufferSizeChanged();

    // Trim buffer if needed
    QMutexLocker locker(&m_bufferMutex);
    while (m_frameBuffer.size() > static_cast<size_t>(m_maxBufferSize)) {
        m_frameBuffer.pop_front();
    }
}

VideoFramePacket VideoBackend::getFrameAtTime(double lslTimestamp) const
{
    QMutexLocker locker(&m_bufferMutex);

    if (m_frameBuffer.empty())
        return VideoFramePacket();

    // Binary search: std::lower_bound returns the first frame with timestamp
    // >= lslTimestamp, then we check the previous frame to pick the closer one.
    // This is O(log N) in the buffer size (~300 entries).
    auto it = std::lower_bound(
        m_frameBuffer.begin(),
        m_frameBuffer.end(),
        lslTimestamp,
        [](const VideoFramePacket& packet, double timestamp) {
            return packet.lslTimestamp < timestamp;
        });

    if (it == m_frameBuffer.end()) {
        // Timestamp is after all frames, return last frame
        return m_frameBuffer.back();
    }

    if (it == m_frameBuffer.begin()) {
        // Timestamp is before all frames, return first frame
        return m_frameBuffer.front();
    }

    // Check which neighbor is closer
    auto prevIt = std::prev(it);
    double diffCurrent = std::abs(it->lslTimestamp - lslTimestamp);
    double diffPrev = std::abs(prevIt->lslTimestamp - lslTimestamp);

    return (diffPrev < diffCurrent) ? *prevIt : *it;
}

QVariantList VideoBackend::getFrameTimestamps() const
{
    QMutexLocker locker(&m_bufferMutex);

    QVariantList result;
    for (const auto& packet : m_frameBuffer) {
        result.append(packet.lslTimestamp);
    }
    return result;
}

double VideoBackend::getLatestTimestamp() const
{
    QMutexLocker locker(&m_bufferMutex);

    if (m_frameBuffer.empty()) {
        return 0.0;
    }
    return m_frameBuffer.back().lslTimestamp;
}

double VideoBackend::getOldestTimestamp() const
{
    QMutexLocker locker(&m_bufferMutex);

    if (m_frameBuffer.empty()) {
        return 0.0;
    }
    return m_frameBuffer.front().lslTimestamp;
}

std::deque<VideoFramePacket> VideoBackend::frameBuffer() const
{
    QMutexLocker locker(&m_bufferMutex);
    return m_frameBuffer;
}

void VideoBackend::clearBuffer()
{
    QMutexLocker locker(&m_bufferMutex);
    m_frameBuffer.clear();
    emit statsUpdated();
}

void VideoBackend::onFrameReady(const VideoFramePacket& packet)
{
    if (!packet.isValid()) {
        return;
    }

    // Add to buffer
    addFrameToBuffer(packet);

    // Update statistics
    m_frameCount++;
    m_lastFrameTimestamp = packet.lslTimestamp;

    // Update video sink for display
    if (m_videoSink) {
        updateVideoSink(packet.frame);
    }

    emit frameReceived(packet.lslTimestamp);
}

void VideoBackend::addFrameToBuffer(const VideoFramePacket& packet)
{
    QMutexLocker locker(&m_bufferMutex);

    m_frameBuffer.push_back(packet);

    // Maintain buffer size limit
    while (m_frameBuffer.size() > static_cast<size_t>(m_maxBufferSize)) {
        m_frameBuffer.pop_front();
    }
}

void VideoBackend::updateVideoSink(const QImage& image)
{
    if (!m_videoSink || image.isNull()) {
        return;
    }

    // Convert QImage to QVideoFrame
    QVideoFrame frame(image);
    m_videoSink->setVideoFrame(frame);
}

void VideoBackend::onCameraError(const QString& error)
{
    qWarning() << "VideoBackend: Camera error:" << error;

    m_isConnected = false;
    emit isConnectedChanged();
    emit errorOccurred(error);
}
