#pragma once

// PiControlPoller — periodic status poller around PiControlClient.
//
// Mirrors the Python ControlPoller in pi_camera/pc_app/pi_control.py, but
// without a worker thread: Qt's network stack is already async, so polling
// is just a QTimer + a few signal connections. One poller per Pi.
//
// What it does on a tick (default: 1 Hz):
//   - fetchStatus()
//   - every Nth tick (default: every 30): also fetchOptions + fetchChannels
//     (these change rarely; no need to hammer the daemon)
//
// The dock UI binds to snapshotChanged() and reads the cached getters. The
// caller can still send commands at any time via sendControl() /
// sendImpedance() (forwarded to the client) and listen to the
// controlResult / impedanceResult signals re-emitted from the client.

#include <QJsonObject>
#include <QObject>
#include <QStringList>

class PiControlClient;
class QTimer;

class PiControlPoller : public QObject
{
    Q_OBJECT
public:
    explicit PiControlPoller(PiControlClient *client, QObject *parent = nullptr);

    // Cached state — safe to read from the GUI thread at any time.
    bool        reachable() const { return m_reachable; }
    bool        daemonUp()  const { return m_daemonUp; }
    QJsonObject status()    const { return m_status; }
    QJsonObject options()   const { return m_options; }
    QStringList channels()  const { return m_channels; }

    // True once we've decided whether the Pi is reachable or not (either
    // first successful poll, or N consecutive failures). Before that the
    // UI shows "connecting…" so a single slow / racy mDNS lookup at startup
    // doesn't flash "Pi unreachable" before the next poll succeeds.
    bool        confirmed() const { return m_uiConfirmed; }

    PiControlClient *client() const { return m_client; }

public slots:
    void start(int periodMs = 1000);
    void stop();

    // Force a fresh connection: drop+recreate the QNetworkAccessManager
    // (clears DNS+conn cache), reset the failure counter, and poll
    // immediately. UI flips back to "connecting…" until the next response.
    void reconnect();

    // Convenience pass-throughs to the underlying client.
    void sendControl(const QJsonObject &patch);
    void sendImpedance(int durationSec);

signals:
    // Any of status / options / channels / reachability flipped.
    void snapshotChanged();
    // Pass-through from the client (so the UI only binds to the poller).
    void controlResult(int httpCode, QJsonObject payload);
    void impedanceResult(int httpCode, QJsonObject payload);

private slots:
    void onTick();
    void onStatus(int code, QJsonObject payload);
    void onOptions(int code, QJsonObject payload);
    void onChannels(int code, QStringList channels, QJsonObject payload);

private:
    PiControlClient *m_client = nullptr;
    QTimer          *m_timer  = nullptr;

    bool        m_reachable = false;
    bool        m_daemonUp  = false;
    QJsonObject m_status;
    QJsonObject m_options;
    QStringList m_channels;

    int  m_metaEvery     = 30;       // refresh options+channels every N ticks
    int  m_metaCountdown = 0;

    // ---- failure debounce ----
    // We don't flip the UI to "unreachable" on a single failed poll: a
    // racy mDNS lookup or a busy Pi can cause one isolated timeout. Only
    // after this many consecutive failed /status polls do we say the Pi
    // is unreachable. (At 1 s/poll + 4 s transfer timeout, this means
    // ~5-12 s before the UI gives up.)
    static constexpr int kFailureThreshold = 3;
    int  m_consecFailures = 0;
    // False until either the first successful response OR
    // kFailureThreshold consecutive failures. UI shows "connecting…"
    // until this flips.
    bool m_uiConfirmed = false;
};
