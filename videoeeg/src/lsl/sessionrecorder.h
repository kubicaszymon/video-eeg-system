#pragma once

#include <QString>

#include <atomic>
#include <mutex>
#include <thread>
#include <vector>

// ---------------------------------------------------------------------------
// SessionRecorder — loss-less synchronized recorder.
//
// A C++ port of the Python `Recorder` in pi_camera/pc_app/sync_prototype.py.
// It records BOTH LSL streams from its OWN inlets, completely independent of
// the on-screen receivers (LslEegReceiver / LslVideoReceiver). LSL allows many
// consumers, so a laggy or paused UI can never corrupt or starve the
// recording. In addition it logs periodic per-stream time_correction values so
// the two streams can be realised onto the common LSL clock offline — the same
// principle LabRecorder/XDF uses.
//
// The on-disk layout is byte-for-byte the format documented in
// VIDEO_EEG_APP_SPEC.md and produced by the Python tool, so the existing
// pc_examples/check_session.py and xdf tooling read C++-recorded sessions
// unchanged:
//
//   session_YYYYmmdd-HHMMSS/
//     meta.json          stream names, eeg channels, srate, start times
//     eeg_samples.f32    raw float32, row-major  [frame][channel]
//     eeg_ts.f64         raw float64, one LSL timestamp per frame
//     video.h264         concatenated Annex-B H.264 access units
//     video_index.csv    ts,keyframe,nbytes  (one row per access unit)
//     clock.csv          local_clock,stream,time_correction  (~0.5 Hz)
//
// Threading: three std::threads (eeg / video / clock), each owning its own
// liblsl inlet. No Qt types are needed on the worker side, so this is a plain
// class (not a QObject); the GUI thread only calls start()/stop()/stats().
// ---------------------------------------------------------------------------
class SessionRecorder
{
public:
    struct Stats {
        long long eegSamples = 0;   // EEG frames written
        long long videoAUs   = 0;   // H.264 access units written
        long long bytes      = 0;   // H.264 bytes written
    };

    SessionRecorder(QString eegName, QString videoName, QString root);
    ~SessionRecorder();

    // Create session_YYYYmmdd-HHMMSS/ under `root` and spawn the worker
    // threads. The session metadata is captured into meta.json. Returns the
    // absolute session directory on success, or an empty string on failure
    // (see lastError()).
    QString start(const QString &subject,
                  const QString &op,
                  const QString &notes);

    // Signal the workers to stop and join them (bounded wait). Files are
    // flushed and closed. Safe to call more than once.
    void stop();

    bool    active() const { return m_active.load(); }
    Stats   stats() const;
    QString dir() const;
    QString lastError() const;

private:
    void eegLoop();
    void videoLoop();
    void clockLoop();

    void setError(const QString &e);

    const QString m_eegName;
    const QString m_videoName;
    const QString m_root;

    // Session metadata captured at start().
    QString m_subject;
    QString m_op;
    QString m_notes;
    double  m_startedUnix       = 0.0;
    double  m_startedLocalClock = 0.0;

    std::atomic<bool> m_stop{false};
    std::atomic<bool> m_active{false};
    std::vector<std::thread> m_threads;

    mutable std::mutex m_mutex;     // guards m_dir / m_stats / m_error
    QString m_dir;
    Stats   m_stats;
    QString m_error;
};
