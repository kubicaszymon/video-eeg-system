#pragma once

// LslEegReceiver — background QThread that pulls the Perun32 EEG stream
// from LSL and maintains a thread-safe ring buffer of recent samples.
//
// Mirrors the EegReceiver pattern in pi_camera/pc_app/sync_prototype.py:
//   - dedicated worker thread (LSL pull_chunk is blocking)
//   - resolves the stream by name (auto-reconnect on stream drop)
//   - read channel metadata from the LSL stream description
//   - exposes a thread-safe snapshot() for the GUI thread to read
//   - emits Qt signals (streamResolved / chunkReceived) so the UI repaints
//
// Hides liblsl entirely behind the cpp -- the header uses only Qt + std.
// (Otherwise every translation unit that includes this would pull in all
// of liblsl, lslboost, etc.)

#include <QMutex>
#include <QString>
#include <QStringList>
#include <QThread>

#include <atomic>
#include <memory>
#include <vector>

class LslEegReceiver : public QThread
{
    Q_OBJECT
public:
    explicit LslEegReceiver(const QString &streamName,
                            double bufferSeconds = 10.0,
                            QObject *parent = nullptr);
    ~LslEegReceiver() override;

    // Ask the worker thread to stop and join. Safe to call multiple times.
    void shutdown();

    // ---- introspection (thread-safe; readable from the GUI thread) ----

    struct ChannelInfo {
        QString label;    // e.g. "ExG_1"
        QString type;     // "EEG" | "impedance" | ...
        QString unit;     // "microvolts" | "ohms" | ...
    };

    struct Info {
        QString name;                       // resolved stream name
        int     channelCount = 0;
        double  nominalSrate = 0.0;
        QVector<ChannelInfo> channels;
        // Indices into `channels` for the two logical groups; either may be
        // empty depending on producer config (e.g. plain EEG = no impedance).
        QVector<int> signalIdx;
        QVector<int> impedanceIdx;
    };

    bool connected() const;     // true if the inlet is currently bound
    Info info() const;          // empty Info until streamResolved() fires

    // Snapshot of the most recent samples. Output is row-major
    // [frames * channels] floats + [frames] timestamps. Returns 0 frames if
    // nothing buffered yet. `maxFrames < 0` means "everything available".
    struct Snapshot {
        std::vector<float>  samples;    // size = frames * channels
        std::vector<double> timestamps; // size = frames (LSL clock, seconds)
        int frames   = 0;
        int channels = 0;
    };
    Snapshot snapshot(int maxFrames = -1) const;

signals:
    // Emitted once the LSL inlet is open and Info has been populated.
    // Cross-thread safe (Qt::AutoConnection -> QueuedConnection to GUI).
    void streamResolved();

    // Emitted after a non-empty pull_chunk; the GUI may snapshot now.
    void chunkReceived();

    // Stream visible to the network but the inlet just lost it (rate change,
    // impedance pass, daemon restart). UI may show "reconnecting…".
    void streamLost();

protected:
    void run() override;

private:
    // ---- worker-thread-only helpers ----
    void readMeta();                                    // populates m_info
    void allocateRing(int channels);
    void pushChunk(const std::vector<std::vector<float>> &chunk,
                   const std::vector<double> &timestamps);

    // ---- config ----
    QString m_name;
    double  m_bufferSeconds;

    // ---- worker state (touched only by the worker thread) ----
    struct InletHolder;                                 // PIMPL for lsl::stream_inlet
    std::unique_ptr<InletHolder> m_holder;

    // ---- shared state (guarded by m_mutex) ----
    mutable QMutex m_mutex;
    Info  m_info;
    bool  m_connected = false;

    // Contiguous ring buffer; allocated after the inlet is opened so its
    // channel count is known.
    std::vector<float>  m_ring;        // size = m_ringFrames * m_info.channelCount
    std::vector<double> m_ringTs;      // size = m_ringFrames
    int  m_ringFrames = 0;             // capacity in frames
    int  m_writeHead  = 0;             // next frame to overwrite
    qint64 m_totalWritten = 0;         // monotonically increasing

    std::atomic<bool> m_stopRequested{false};
};
