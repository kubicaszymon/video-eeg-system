#include "lsleegreceiver.h"

#include <lsl_cpp.h>

#include <QDebug>
#include <QMutexLocker>

#include <algorithm>
#include <chrono>
#include <cstring>

// PIMPL: the liblsl inlet lives only in the .cpp so the header doesn't drag
// boost/lsl into every translation unit.
struct LslEegReceiver::InletHolder
{
    std::unique_ptr<lsl::stream_inlet> inlet;
};

// --------------------------------------------------------------------------
// Lifecycle
// --------------------------------------------------------------------------

LslEegReceiver::LslEegReceiver(const QString &streamName,
                               double bufferSeconds, QObject *parent)
    : QThread(parent),
      m_name(streamName),
      m_bufferSeconds(bufferSeconds),
      m_holder(std::make_unique<InletHolder>())
{}

LslEegReceiver::~LslEegReceiver()
{
    shutdown();
}

void LslEegReceiver::shutdown()
{
    m_stopRequested.store(true);
    // Closing the inlet from another thread is documented as safe in liblsl
    // and is the cleanest way to unblock pull_chunk(). The worker thread
    // sees the exception and exits its loop.
    if (m_holder && m_holder->inlet)
        m_holder->inlet->close_stream();
    if (isRunning()) {
        if (!wait(2000))
            terminate();        // last-resort
    }
}

// --------------------------------------------------------------------------
// Thread-safe accessors (GUI thread reads these)
// --------------------------------------------------------------------------

bool LslEegReceiver::connected() const
{
    QMutexLocker lock(&m_mutex);
    return m_connected;
}

LslEegReceiver::Info LslEegReceiver::info() const
{
    QMutexLocker lock(&m_mutex);
    return m_info;
}

LslEegReceiver::Snapshot LslEegReceiver::snapshot(int maxFrames) const
{
    QMutexLocker lock(&m_mutex);
    Snapshot s;
    if (m_info.channelCount <= 0 || m_ringFrames <= 0)
        return s;

    const qint64 available = std::min<qint64>(m_totalWritten, m_ringFrames);
    int n = static_cast<int>(available);
    if (maxFrames >= 0 && maxFrames < n)
        n = maxFrames;
    if (n <= 0)
        return s;

    s.frames   = n;
    s.channels = m_info.channelCount;
    s.samples.resize(static_cast<size_t>(n) * m_info.channelCount);
    s.timestamps.resize(static_cast<size_t>(n));

    // Oldest of the requested window starts at (writeHead - n + ringFrames) % ringFrames.
    const int start = (m_writeHead - n + m_ringFrames) % m_ringFrames;
    if (start + n <= m_ringFrames) {
        // contiguous
        std::memcpy(s.samples.data(),
                    m_ring.data() + start * m_info.channelCount,
                    static_cast<size_t>(n) * m_info.channelCount * sizeof(float));
        std::memcpy(s.timestamps.data(),
                    m_ringTs.data() + start,
                    static_cast<size_t>(n) * sizeof(double));
    } else {
        const int firstChunk = m_ringFrames - start;
        std::memcpy(s.samples.data(),
                    m_ring.data() + start * m_info.channelCount,
                    static_cast<size_t>(firstChunk) * m_info.channelCount * sizeof(float));
        std::memcpy(s.samples.data() + firstChunk * m_info.channelCount,
                    m_ring.data(),
                    static_cast<size_t>(n - firstChunk) * m_info.channelCount * sizeof(float));
        std::memcpy(s.timestamps.data(),
                    m_ringTs.data() + start,
                    static_cast<size_t>(firstChunk) * sizeof(double));
        std::memcpy(s.timestamps.data() + firstChunk,
                    m_ringTs.data(),
                    static_cast<size_t>(n - firstChunk) * sizeof(double));
    }
    return s;
}

// --------------------------------------------------------------------------
// Worker thread
// --------------------------------------------------------------------------

void LslEegReceiver::run()
{
    using namespace std::chrono_literals;

    while (!m_stopRequested.load()) {
        // ---- resolve + open -----------------------------------------------
        try {
            auto streams = lsl::resolve_stream(
                "name", m_name.toStdString(), /*minimum=*/1, /*timeout=*/1.0);
            if (streams.empty()) {
                std::this_thread::sleep_for(500ms);
                continue;
            }
            m_holder->inlet = std::make_unique<lsl::stream_inlet>(
                streams[0],
                /*max_buflen_seconds=*/static_cast<int>(m_bufferSeconds),
                /*max_chunklen=*/0,
                /*recover=*/false);   // we manage reconnects ourselves
            readMeta();
            allocateRing(m_info.channelCount);
            {
                QMutexLocker lock(&m_mutex);
                m_connected = true;
            }
            emit streamResolved();
        } catch (const std::exception &exc) {
            qWarning() << "LslEegReceiver: resolve/open failed:" << exc.what();
            std::this_thread::sleep_for(500ms);
            continue;
        }

        // ---- pull loop -----------------------------------------------------
        // liblsl's stream_inlet::pull_chunk(vec, vec) is *non-blocking* in
        // this version (1.17.5) -- it returns whatever's currently buffered
        // and bails out immediately if nothing is available. So we drive the
        // loop ourselves and sleep briefly between empty pulls. The sleep is
        // short so shutdown() stays responsive.
        std::vector<std::vector<float>> chunk;
        std::vector<double> tstamps;
        try {
            while (!m_stopRequested.load()) {
                chunk.clear();
                tstamps.clear();
                const bool gotAny = m_holder->inlet->pull_chunk(chunk, tstamps);
                if (gotAny && !chunk.empty()) {
                    pushChunk(chunk, tstamps);
                    emit chunkReceived();
                } else {
                    std::this_thread::sleep_for(20ms);
                }
            }
        } catch (const lsl::lost_error &) {
            qWarning() << "LslEegReceiver: stream lost, will reconnect";
        } catch (const std::exception &exc) {
            qWarning() << "LslEegReceiver: pull failed:" << exc.what();
        }

        m_holder->inlet.reset();
        {
            QMutexLocker lock(&m_mutex);
            m_connected = false;
        }
        emit streamLost();
    }
}

// --------------------------------------------------------------------------
// Meta + ringbuffer (worker thread only)
// --------------------------------------------------------------------------

void LslEegReceiver::readMeta()
{
    // Not `const`: lsl::stream_info::desc() is non-const in liblsl 1.17.5.
    lsl::stream_info inf = m_holder->inlet->info(2.0);
    Info out;
    out.name         = QString::fromStdString(inf.name());
    out.channelCount = inf.channel_count();
    out.nominalSrate = inf.nominal_srate();

    lsl::xml_element ch = inf.desc().child("channels").child("channel");
    for (int i = 0; i < out.channelCount; ++i) {
        ChannelInfo c;
        // mirror the python: prefer "label" then "name"
        std::string lab = ch.child_value("label");
        if (lab.empty()) lab = ch.child_value("name");
        c.label = QString::fromStdString(lab);
        c.type  = QString::fromStdString(ch.child_value("type"));
        c.unit  = QString::fromStdString(ch.child_value("unit"));
        if (c.type.compare(QLatin1String("impedance"),
                            Qt::CaseInsensitive) == 0)
            out.impedanceIdx.append(i);
        else
            out.signalIdx.append(i);
        out.channels.append(c);
        ch = ch.next_sibling("channel");
    }

    QMutexLocker lock(&m_mutex);
    m_info = out;
}

void LslEegReceiver::allocateRing(int channels)
{
    const double rate = std::max(1.0, m_info.nominalSrate);
    const int frames = std::max(1, static_cast<int>(m_bufferSeconds * rate));

    QMutexLocker lock(&m_mutex);
    m_ring.assign(static_cast<size_t>(frames) * channels, 0.0f);
    m_ringTs.assign(static_cast<size_t>(frames), 0.0);
    m_ringFrames   = frames;
    m_writeHead    = 0;
    m_totalWritten = 0;
}

void LslEegReceiver::pushChunk(const std::vector<std::vector<float>> &chunk,
                                const std::vector<double> &timestamps)
{
    if (chunk.empty()) return;
    const int channels = m_info.channelCount;
    const int frames   = static_cast<int>(chunk.size());

    QMutexLocker lock(&m_mutex);
    if (m_ringFrames <= 0 || channels <= 0)
        return;

    for (int i = 0; i < frames; ++i) {
        if (static_cast<int>(chunk[i].size()) != channels)
            continue;                       // protocol violation; skip
        std::memcpy(m_ring.data() + m_writeHead * channels,
                    chunk[i].data(),
                    static_cast<size_t>(channels) * sizeof(float));
        m_ringTs[m_writeHead] = (i < static_cast<int>(timestamps.size()))
                                    ? timestamps[i] : 0.0;
        m_writeHead = (m_writeHead + 1) % m_ringFrames;
        ++m_totalWritten;
    }
}
