#include "sessionrecorder.h"

#include <lsl_cpp.h>

#include <QByteArray>
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <chrono>
#include <fstream>
#include <memory>

// ---------------------------------------------------------------------------
// Small helpers (file-local)
// ---------------------------------------------------------------------------
namespace {

using namespace std::chrono_literals;

// Open a binary output stream for a QString path. On MSVC std::ofstream
// accepts a wide path, which avoids code-page issues with the file name.
std::ofstream openBinary(const QString &path)
{
#if defined(_WIN32)
    return std::ofstream(path.toStdWString(), std::ios::binary);
#else
    return std::ofstream(path.toStdString(), std::ios::binary);
#endif
}

// Resolve a stream by name into an inlet, retrying until `stop` is set.
// Returns nullptr only if stop was requested before the stream appeared.
// max_buflen=60 s, recover=true mirror the Python recorder's inlet.
std::unique_ptr<lsl::stream_inlet> resolveInlet(const QString &name,
                                                const std::atomic<bool> &stop)
{
    while (!stop.load()) {
        try {
            auto streams = lsl::resolve_stream("name", name.toStdString(),
                                               /*minimum=*/1, /*timeout=*/1.0);
            if (!streams.empty()) {
                return std::make_unique<lsl::stream_inlet>(
                    streams[0], /*max_buflen=*/60, /*max_chunklen=*/0,
                    /*recover=*/true);
            }
        } catch (const std::exception &exc) {
            qWarning() << "SessionRecorder: resolve failed:" << exc.what();
        }
    }
    return nullptr;
}

QByteArray fixed9(double v)            // "%.9f", matching the Python tool
{
    return QByteArray::number(v, 'f', 9);
}

} // namespace

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

SessionRecorder::SessionRecorder(QString eegName, QString videoName,
                                 QString root)
    : m_eegName(std::move(eegName)),
      m_videoName(std::move(videoName)),
      m_root(std::move(root))
{}

SessionRecorder::~SessionRecorder()
{
    stop();
}

QString SessionRecorder::start(const QString &subject, const QString &op,
                               const QString &notes)
{
    if (m_active.load())
        return dir();                  // already recording

    m_subject = subject;
    m_op      = op;
    m_notes   = notes;

    const QString stamp =
        QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss"));
    const QString sessionDir =
        QDir(m_root).filePath(QStringLiteral("session_%1").arg(stamp));

    if (!QDir().mkpath(sessionDir)) {
        setError(QStringLiteral("could not create %1").arg(sessionDir));
        return {};
    }

    m_startedUnix       = static_cast<double>(
        QDateTime::currentMSecsSinceEpoch()) / 1000.0;
    m_startedLocalClock = lsl::local_clock();

    {
        std::lock_guard<std::mutex> lk(m_mutex);
        m_dir   = sessionDir;
        m_stats = Stats{};
        m_error.clear();
    }

    m_stop.store(false);
    m_active.store(true);
    m_threads.clear();
    m_threads.emplace_back(&SessionRecorder::eegLoop,   this);
    m_threads.emplace_back(&SessionRecorder::videoLoop, this);
    m_threads.emplace_back(&SessionRecorder::clockLoop, this);

    return sessionDir;
}

void SessionRecorder::stop()
{
    if (!m_active.exchange(false) && m_threads.empty())
        return;
    m_stop.store(true);
    for (auto &t : m_threads) {
        if (t.joinable())
            t.join();
    }
    m_threads.clear();
}

// ---------------------------------------------------------------------------
// Accessors
// ---------------------------------------------------------------------------

SessionRecorder::Stats SessionRecorder::stats() const
{
    std::lock_guard<std::mutex> lk(m_mutex);
    return m_stats;
}

QString SessionRecorder::dir() const
{
    std::lock_guard<std::mutex> lk(m_mutex);
    return m_dir;
}

QString SessionRecorder::lastError() const
{
    std::lock_guard<std::mutex> lk(m_mutex);
    return m_error;
}

void SessionRecorder::setError(const QString &e)
{
    qWarning() << "SessionRecorder:" << e;
    std::lock_guard<std::mutex> lk(m_mutex);
    if (m_error.isEmpty())
        m_error = e;
}

// ---------------------------------------------------------------------------
// EEG worker: meta.json + eeg_samples.f32 + eeg_ts.f64
// ---------------------------------------------------------------------------

void SessionRecorder::eegLoop()
{
    auto inlet = resolveInlet(m_eegName, m_stop);
    if (!inlet)
        return;

    int nch = 0;
    QStringList labels;
    double srate = 0.0;
    try {
        lsl::stream_info inf = inlet->info(5.0);
        nch   = inf.channel_count();
        srate = inf.nominal_srate();
        lsl::xml_element ch = inf.desc().child("channels").child("channel");
        for (int i = 0; i < nch; ++i) {
            std::string lab = ch.child_value("label");
            if (lab.empty()) lab = ch.child_value("name");
            labels << QString::fromStdString(lab);
            ch = ch.next_sibling("channel");
        }
    } catch (const std::exception &exc) {
        setError(QStringLiteral("eeg info: %1").arg(exc.what()));
        return;
    }
    if (nch <= 0) {
        setError(QStringLiteral("eeg stream has 0 channels"));
        return;
    }

    // ---- meta.json (written once, here, where we have the channel info) ----
    {
        QJsonObject meta;
        meta[QStringLiteral("eeg_name")]   = m_eegName;
        meta[QStringLiteral("video_name")] = m_videoName;
        meta[QStringLiteral("eeg_nch")]    = nch;
        QJsonArray chans;
        for (const QString &l : labels) chans.append(l);
        meta[QStringLiteral("eeg_channels")]      = chans;
        meta[QStringLiteral("eeg_srate_nominal")] = srate;
        meta[QStringLiteral("started_unix")]       = m_startedUnix;
        meta[QStringLiteral("started_localclock")] = m_startedLocalClock;
        meta[QStringLiteral("subject")]  = m_subject;
        meta[QStringLiteral("operator")] = m_op;
        meta[QStringLiteral("notes")]    = m_notes;

        std::ofstream fm = openBinary(QDir(dir()).filePath(
            QStringLiteral("meta.json")));
        if (fm) {
            const QByteArray j =
                QJsonDocument(meta).toJson(QJsonDocument::Indented);
            fm.write(j.constData(), j.size());
        } else {
            setError(QStringLiteral("could not open meta.json"));
        }
    }

    std::ofstream fs = openBinary(QDir(dir()).filePath(
        QStringLiteral("eeg_samples.f32")));
    std::ofstream ft = openBinary(QDir(dir()).filePath(
        QStringLiteral("eeg_ts.f64")));
    if (!fs || !ft) {
        setError(QStringLiteral("could not open eeg output files"));
        return;
    }

    std::vector<std::vector<float>> chunk;
    std::vector<double> tstamps;
    long long written = 0;
    try {
        while (!m_stop.load()) {
            chunk.clear();
            tstamps.clear();
            const bool got = inlet->pull_chunk(chunk, tstamps);
            if (!got || chunk.empty()) {
                std::this_thread::sleep_for(20ms);
                continue;
            }
            for (size_t i = 0; i < chunk.size(); ++i) {
                if (static_cast<int>(chunk[i].size()) != nch)
                    continue;                       // protocol violation; skip
                fs.write(reinterpret_cast<const char *>(chunk[i].data()),
                         static_cast<std::streamsize>(nch) * sizeof(float));
                const double ts = (i < tstamps.size()) ? tstamps[i] : 0.0;
                ft.write(reinterpret_cast<const char *>(&ts), sizeof(double));
                ++written;
            }
            std::lock_guard<std::mutex> lk(m_mutex);
            m_stats.eegSamples = written;
        }
    } catch (const std::exception &exc) {
        setError(QStringLiteral("eeg pull: %1").arg(exc.what()));
    }
}

// ---------------------------------------------------------------------------
// Video worker: video.h264 + video_index.csv
// ---------------------------------------------------------------------------

void SessionRecorder::videoLoop()
{
    auto inlet = resolveInlet(m_videoName, m_stop);
    if (!inlet)
        return;

    std::ofstream fv = openBinary(QDir(dir()).filePath(
        QStringLiteral("video.h264")));
    std::ofstream fi = openBinary(QDir(dir()).filePath(
        QStringLiteral("video_index.csv")));
    if (!fv || !fi) {
        setError(QStringLiteral("could not open video output files"));
        return;
    }
    fi << "ts,keyframe,nbytes\n";

    std::vector<std::vector<std::string>> chunk;
    std::vector<double> tstamps;
    long long aus = 0;
    long long bytes = 0;
    try {
        while (!m_stop.load()) {
            chunk.clear();
            tstamps.clear();
            const bool got = inlet->pull_chunk(chunk, tstamps);
            if (!got || chunk.empty()) {
                std::this_thread::sleep_for(10ms);
                continue;
            }
            for (size_t i = 0; i < chunk.size(); ++i) {
                if (chunk[i].size() < 2)
                    continue;
                const std::string &b64 = chunk[i][0];
                const bool key = (chunk[i][1] == "1");
                const QByteArray data = QByteArray::fromBase64(
                    QByteArray::fromRawData(b64.data(),
                                            static_cast<int>(b64.size())));
                if (data.isEmpty())
                    continue;
                fv.write(data.constData(), data.size());

                const double ts = (i < tstamps.size()) ? tstamps[i] : 0.0;
                fi << fixed9(ts).constData() << ',' << (key ? 1 : 0) << ','
                   << data.size() << '\n';

                ++aus;
                bytes += data.size();
            }
            std::lock_guard<std::mutex> lk(m_mutex);
            m_stats.videoAUs = aus;
            m_stats.bytes    = bytes;
        }
    } catch (const std::exception &exc) {
        setError(QStringLiteral("video pull: %1").arg(exc.what()));
    }
}

// ---------------------------------------------------------------------------
// Clock worker: clock.csv (periodic time_correction per stream)
// ---------------------------------------------------------------------------

void SessionRecorder::clockLoop()
{
    auto eeg = resolveInlet(m_eegName, m_stop);
    auto vid = resolveInlet(m_videoName, m_stop);

    std::ofstream fc = openBinary(QDir(dir()).filePath(
        QStringLiteral("clock.csv")));
    if (!fc) {
        setError(QStringLiteral("could not open clock.csv"));
        return;
    }
    fc << "local_clock,stream,time_correction\n";

    const struct { const char *name; lsl::stream_inlet *inl; } pairs[] = {
        {"eeg",   eeg.get()},
        {"video", vid.get()},
    };

    while (!m_stop.load()) {
        for (const auto &p : pairs) {
            if (!p.inl)
                continue;
            try {
                const double tc = p.inl->time_correction(0.5);
                fc << fixed9(lsl::local_clock()).constData() << ','
                   << p.name << ',' << fixed9(tc).constData() << '\n';
            } catch (const std::exception &) {
                // best-effort; skip this tick for this stream
            }
        }
        fc.flush();
        // Sleep ~2 s but stay responsive to stop().
        for (int i = 0; i < 20 && !m_stop.load(); ++i)
            std::this_thread::sleep_for(100ms);
    }
}
