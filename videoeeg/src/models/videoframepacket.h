/*
 * ==========================================================================
 *  videoframepacket.h — Video Frame & Camera Configuration Data Structures
 * ==========================================================================
 *
 *  PURPOSE:
 *    Defines the plain-data structures shared between the camera capture
 *    layer (CameraManager), the video display layer (VideoBackend), and
 *    the recording system (RecordingManager).
 *
 *    These are value types (Q_GADGET, not Q_OBJECT) — they are copied by
 *    value across the signal/slot boundary, which is safe because the
 *    QImage inside VideoFramePacket uses implicit sharing (copy-on-write).
 *
 *  LSL TIMESTAMP SIGNIFICANCE:
 *    Every VideoFramePacket carries an lslTimestamp stamped by
 *    lsl::local_clock() at the exact moment onVideoFrameChanged() fires.
 *    This is the same time base used by EEG samples from the amplifier,
 *    making it possible to find the EEG sample that matches each frame
 *    by searching EegSyncManager's buffer for the closest timestamp.
 *
 *  DATA FLOW:
 *    QVideoSink::videoFrameChanged()
 *      → CameraManager::onVideoFrameChanged()
 *          stamps frame with lsl::local_clock()
 *          emits frameReady(VideoFramePacket)
 *      → VideoBackend::onFrameReady()
 *          stores in m_frameBuffer (indexed by lslTimestamp)
 *          emits frameReceived(lslTimestamp)
 *      → EegSyncManager::getEEGForFrame(lslTimestamp)
 *          returns EEG data aligned to this frame
 *
 * ==========================================================================
 */

#ifndef VIDEOFRAMEPACKET_H
#define VIDEOFRAMEPACKET_H

#include <QImage>
#include <QObject>
#include <QtQml/qqmlregistration.h>

/*
 * VideoFramePacket — a single captured video frame with its LSL timestamp.
 *
 * NOTE on isValid(): The frame field is intentionally empty when CameraManager
 * operates in timestamp-only mode (i.e. startCapture() with no QImage
 * conversion). In that mode lslTimestamp > 0 is the only reliability check
 * that matters; callers that need the image must check frame.isNull() separately.
 */
struct VideoFramePacket
{
    Q_GADGET
    Q_PROPERTY(double lslTimestamp MEMBER lslTimestamp)
    Q_PROPERTY(qint64 frameNumber MEMBER frameNumber)

public:
    QImage  frame;          // Captured video frame (may be null in timestamp-only mode)
    double  lslTimestamp;   // lsl::local_clock() value at the instant of capture
    qint64  frameNumber;    // Monotonically increasing frame counter (session-relative)

    VideoFramePacket() : lslTimestamp(0.0), frameNumber(0) {}

    VideoFramePacket(const QImage& img, double timestamp, qint64 number = 0)
        : frame(img), lslTimestamp(timestamp), frameNumber(number) {}

    // Returns true when the packet carries both a valid image and timestamp.
    bool isValid() const { return !frame.isNull() && lslTimestamp > 0.0; }
};

Q_DECLARE_METATYPE(VideoFramePacket)

/*
 * CameraFormat — one entry in the device's supported format list.
 *
 * Populated from QCameraDevice::videoFormats() during enumeration and stored
 * in CameraInfo::formats. The toString() / resolutionString() helpers provide
 * display strings for QML ComboBox delegates.
 */
struct CameraFormat
{
    Q_GADGET
    Q_PROPERTY(int width MEMBER width)
    Q_PROPERTY(int height MEMBER height)
    Q_PROPERTY(double minFrameRate MEMBER minFrameRate)
    Q_PROPERTY(double maxFrameRate MEMBER maxFrameRate)

public:
    int    width        = 0;
    int    height       = 0;
    double minFrameRate = 0.0;
    double maxFrameRate = 0.0;

    CameraFormat() = default;

    CameraFormat(int w, int h, double minFps, double maxFps)
        : width(w), height(h), minFrameRate(minFps), maxFrameRate(maxFps) {}

    QString toString() const {
        return QString("%1x%2 @ %3-%4 FPS")
            .arg(width).arg(height)
            .arg(minFrameRate, 0, 'f', 1)
            .arg(maxFrameRate, 0, 'f', 1);
    }

    QString resolutionString() const {
        return QString("%1x%2").arg(width).arg(height);
    }

    bool operator==(const CameraFormat& other) const {
        return width == other.width &&
               height == other.height &&
               qFuzzyCompare(minFrameRate, other.minFrameRate) &&
               qFuzzyCompare(maxFrameRate, other.maxFrameRate);
    }
};

Q_DECLARE_METATYPE(CameraFormat)

/*
 * CameraInfo — a discovered camera device with all its supported formats.
 *
 * Created in CameraManager::refreshCameraList() from QMediaDevices::videoInputs().
 * The id field is a platform-specific opaque identifier (QByteArray as QString)
 * used to re-locate the device in subsequent QMediaDevices calls.
 */
struct CameraInfo
{
    Q_GADGET
    Q_PROPERTY(QString id MEMBER id)
    Q_PROPERTY(QString description MEMBER description)
    Q_PROPERTY(bool isDefault MEMBER isDefault)

public:
    QString            id;           // Platform device identifier (from QCameraDevice::id())
    QString            description;  // Human-readable name (e.g. "Integrated Webcam")
    bool               isDefault = false;
    QList<CameraFormat> formats;     // All formats advertised by the device driver

    CameraInfo() = default;

    CameraInfo(const QString& deviceId, const QString& desc, bool defaultCam = false)
        : id(deviceId), description(desc), isDefault(defaultCam) {}
};

Q_DECLARE_METATYPE(CameraInfo)

#endif // VIDEOFRAMEPACKET_H
