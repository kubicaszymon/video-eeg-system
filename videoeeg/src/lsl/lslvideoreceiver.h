#pragma once

// LslVideoReceiver — background QThread that pulls the Perun32_Video LSL
// stream (H.264 access units, base64-encoded, one per LSL sample) and feeds
// them through an FFmpeg / libavcodec H.264 decoder. The latest decoded
// frame is exposed as a QImage that the VideoCanvas paints.
//
// Mirrors h264_inlet.H264LslReceiver in pi_camera/pc_app/h264_inlet.py:
//   - resolve by name, auto-reconnect on loss
//   - on (re)connect: drop everything until the first keyframe (channel 1
//     == "1") so the decoder has a valid entry point
//   - single-threaded decode (multi-thread "AUTO" clumps frame output, see
//     CLAUDE.md caveat #9)
//
// liblsl + FFmpeg headers are hidden behind a PIMPL Decoder struct so
// downstream code only sees Qt + std types.

#include <QImage>
#include <QMutex>
#include <QString>
#include <QThread>

#include <atomic>
#include <memory>

class LslVideoReceiver : public QThread
{
    Q_OBJECT
public:
    explicit LslVideoReceiver(const QString &streamName,
                              QObject *parent = nullptr);
    ~LslVideoReceiver() override;

    void shutdown();

    struct Info {
        QString name;
        int     width  = 0;
        int     height = 0;
        double  fps    = 0.0;
        QString codec;        // "h264"
    };

    bool   connected() const;
    Info   info() const;

    // Latest decoded frame (BGRA, ready for QPainter::drawImage). Empty
    // QImage until the first keyframe is decoded. Thread-safe; returns a
    // shallow copy so the caller can hold onto it.
    QImage latestFrame() const;
    double latestTimestamp() const;

signals:
    void streamResolved();    // info() now valid
    void frameReady();        // a new decoded frame is available
    void streamLost();        // inlet dropped, will reconnect

protected:
    void run() override;

private:
    void readMeta();
    void handleSample(const std::vector<std::string> &sample,
                      double timestamp);

    QString m_name;

    struct InletHolder;
    struct Decoder;
    std::unique_ptr<InletHolder> m_inlet;
    std::unique_ptr<Decoder>     m_decoder;

    mutable QMutex m_mutex;
    Info   m_info;
    bool   m_connected = false;
    QImage m_latest;
    double m_latestTs = 0.0;

    bool m_resyncing = true;   // wait for a keyframe after connect / loss
    std::atomic<bool> m_stopRequested{false};
};
