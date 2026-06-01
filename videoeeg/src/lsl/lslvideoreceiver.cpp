#include "lslvideoreceiver.h"

#include <lsl_cpp.h>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

#include <QByteArray>
#include <QDebug>
#include <QMutexLocker>

#include <chrono>
#include <cstring>

// --------------------------------------------------------------------------
// PIMPL: liblsl inlet
// --------------------------------------------------------------------------

struct LslVideoReceiver::InletHolder
{
    std::unique_ptr<lsl::stream_inlet> inlet;
};

// --------------------------------------------------------------------------
// PIMPL: FFmpeg H.264 decoder
// --------------------------------------------------------------------------

struct LslVideoReceiver::Decoder
{
    const AVCodec   *codec   = nullptr;
    AVCodecContext  *ctx     = nullptr;
    AVPacket        *packet  = nullptr;
    AVFrame         *frame   = nullptr;
    SwsContext      *sws     = nullptr;
    int              swsW    = 0;
    int              swsH    = 0;
    AVPixelFormat    swsSrcFmt = AV_PIX_FMT_NONE;

    Decoder()
    {
        codec = avcodec_find_decoder(AV_CODEC_ID_H264);
        if (!codec) { qWarning() << "FFmpeg: H.264 decoder not found"; return; }

        ctx = avcodec_alloc_context3(codec);
        // Match the Python h264_inlet.py choice: single-thread.
        // thread_type=AUTO clumps frame output and tanks fps. See CLAUDE.md.
        ctx->thread_count = 1;
        ctx->thread_type  = 0;
        ctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
        if (avcodec_open2(ctx, codec, nullptr) < 0) {
            qWarning() << "FFmpeg: avcodec_open2 failed";
            avcodec_free_context(&ctx);
            return;
        }
        packet = av_packet_alloc();
        frame  = av_frame_alloc();
    }

    ~Decoder()
    {
        if (sws)   sws_freeContext(sws);
        if (frame)  av_frame_free(&frame);
        if (packet) av_packet_free(&packet);
        if (ctx)    avcodec_free_context(&ctx);
    }

    // Drop all decoder state -- called when we lose the stream so a stale
    // reference frame doesn't corrupt the next decode.
    void flush()
    {
        if (ctx) avcodec_flush_buffers(ctx);
    }

    // Decode one Annex-B H.264 access unit. On success writes a BGRA
    // QImage into `out` and returns true. On EAGAIN (no frame yet) returns
    // false but is not an error.
    bool decode(const QByteArray &nal, QImage &out)
    {
        if (!ctx || !packet || !frame || nal.isEmpty()) return false;

        if (av_new_packet(packet, nal.size()) < 0)
            return false;
        std::memcpy(packet->data, nal.constData(), nal.size());

        int ret = avcodec_send_packet(ctx, packet);
        av_packet_unref(packet);
        if (ret < 0)
            return false;

        ret = avcodec_receive_frame(ctx, frame);
        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF)
            return false;
        if (ret < 0)
            return false;

        const int w = frame->width;
        const int h = frame->height;
        const AVPixelFormat srcFmt = static_cast<AVPixelFormat>(frame->format);
        if (w <= 0 || h <= 0) return false;

        if (!sws || swsW != w || swsH != h || swsSrcFmt != srcFmt) {
            if (sws) sws_freeContext(sws);
            // BGRA is what QImage::Format_RGB32 expects on little-endian
            // (the alpha byte is the high byte of a 32-bit word).
            sws = sws_getContext(w, h, srcFmt,
                                 w, h, AV_PIX_FMT_BGRA,
                                 SWS_BILINEAR, nullptr, nullptr, nullptr);
            swsW = w; swsH = h; swsSrcFmt = srcFmt;
            if (!sws) {
                qWarning() << "FFmpeg: sws_getContext failed";
                return false;
            }
        }

        QImage img(w, h, QImage::Format_RGB32);
        uint8_t *dst[1]      = { img.bits() };
        int      dstStride[1] = { static_cast<int>(img.bytesPerLine()) };
        sws_scale(sws, frame->data, frame->linesize, 0, h, dst, dstStride);
        out = img;
        return true;
    }
};

// --------------------------------------------------------------------------
// Lifecycle
// --------------------------------------------------------------------------

LslVideoReceiver::LslVideoReceiver(const QString &streamName, QObject *parent)
    : QThread(parent),
      m_name(streamName),
      m_inlet(std::make_unique<InletHolder>()),
      m_decoder(std::make_unique<Decoder>())
{}

LslVideoReceiver::~LslVideoReceiver()
{
    shutdown();
}

void LslVideoReceiver::shutdown()
{
    m_stopRequested.store(true);
    if (m_inlet && m_inlet->inlet)
        m_inlet->inlet->close_stream();
    if (isRunning()) {
        if (!wait(2000))
            terminate();
    }
}

// --------------------------------------------------------------------------
// Thread-safe accessors
// --------------------------------------------------------------------------

bool LslVideoReceiver::connected() const
{
    QMutexLocker lock(&m_mutex);
    return m_connected;
}

LslVideoReceiver::Info LslVideoReceiver::info() const
{
    QMutexLocker lock(&m_mutex);
    return m_info;
}

QImage LslVideoReceiver::latestFrame() const
{
    QMutexLocker lock(&m_mutex);
    return m_latest;     // QImage uses implicit sharing -- cheap copy
}

double LslVideoReceiver::latestTimestamp() const
{
    QMutexLocker lock(&m_mutex);
    return m_latestTs;
}

// --------------------------------------------------------------------------
// Worker thread
// --------------------------------------------------------------------------

void LslVideoReceiver::run()
{
    using namespace std::chrono_literals;

    while (!m_stopRequested.load()) {
        // ---- resolve + open -----------------------------------------------
        try {
            auto streams = lsl::resolve_stream(
                "name", m_name.toStdString(), 1, 1.0);
            if (streams.empty()) {
                std::this_thread::sleep_for(500ms);
                continue;
            }
            m_inlet->inlet = std::make_unique<lsl::stream_inlet>(
                streams[0], /*max_buflen=*/360, /*max_chunklen=*/0,
                /*recover=*/false);
            readMeta();
            m_resyncing = true;
            m_decoder->flush();
            {
                QMutexLocker lock(&m_mutex);
                m_connected = true;
            }
            emit streamResolved();
        } catch (const std::exception &exc) {
            qWarning() << "LslVideoReceiver: resolve/open failed:" << exc.what();
            std::this_thread::sleep_for(500ms);
            continue;
        }

        // ---- pull loop -----------------------------------------------------
        std::vector<std::vector<std::string>> chunk;
        std::vector<double> tstamps;
        try {
            while (!m_stopRequested.load()) {
                chunk.clear();
                tstamps.clear();
                const bool gotAny = m_inlet->inlet->pull_chunk(chunk, tstamps);
                if (gotAny && !chunk.empty()) {
                    for (size_t i = 0; i < chunk.size(); ++i) {
                        handleSample(chunk[i],
                                     i < tstamps.size() ? tstamps[i] : 0.0);
                    }
                } else {
                    std::this_thread::sleep_for(10ms);
                }
            }
        } catch (const lsl::lost_error &) {
            qWarning() << "LslVideoReceiver: stream lost, will reconnect";
        } catch (const std::exception &exc) {
            qWarning() << "LslVideoReceiver: pull failed:" << exc.what();
        }

        m_inlet->inlet.reset();
        m_decoder->flush();
        {
            QMutexLocker lock(&m_mutex);
            m_connected = false;
        }
        emit streamLost();
    }
}

// --------------------------------------------------------------------------
// Metadata + per-sample handling
// --------------------------------------------------------------------------

void LslVideoReceiver::readMeta()
{
    lsl::stream_info inf = m_inlet->inlet->info(2.0);
    Info out;
    out.name = QString::fromStdString(inf.name());

    // VIDEO_STREAM_SPEC.md says desc/encoding carries codec/width/height/fps.
    lsl::xml_element enc = inf.desc().child("encoding");
    if (!enc.empty()) {
        out.codec  = QString::fromStdString(enc.child_value("codec"));
        out.width  = QString::fromStdString(enc.child_value("width")).toInt();
        out.height = QString::fromStdString(enc.child_value("height")).toInt();
        out.fps    = QString::fromStdString(enc.child_value("fps")).toDouble();
    }

    QMutexLocker lock(&m_mutex);
    m_info = out;
}

void LslVideoReceiver::handleSample(const std::vector<std::string> &sample,
                                    double timestamp)
{
    if (sample.size() < 2) return;

    // After connect (or after a stream loss) we must drop everything until
    // the first keyframe -- the decoder can't recover P-frames without a
    // valid I-frame reference. Mirror of h264_inlet.py's resync logic.
    const bool isKey = (sample[1] == "1");
    if (m_resyncing) {
        if (!isKey) return;
        m_resyncing = false;
    }

    // sample[0] = base64-encoded H.264 access unit. QByteArray::fromBase64
    // tolerates whitespace and produces the raw bytes.
    const QByteArray nal = QByteArray::fromBase64(
        QByteArray::fromRawData(sample[0].data(),
                                static_cast<int>(sample[0].size())));
    if (nal.isEmpty()) return;

    QImage decoded;
    if (m_decoder->decode(nal, decoded)) {
        {
            QMutexLocker lock(&m_mutex);
            m_latest   = decoded;
            m_latestTs = timestamp;
        }
        emit frameReady();
    }
}
