#pragma once

// PiControlClient — async HTTP+JSON client for the Pi streamer control
// daemon (`control_daemon.py`). One instance per Pi (different host+port).
//
// Implements the contract in repo-root CONTROL_API_SPEC.md, the same as
// pi_camera/pc_app/pi_control.py. All calls are non-blocking: each method
// returns immediately and the result arrives on a Qt signal — no threads,
// no event-loop blocking, no `QtConcurrent`. This is the canonical Qt
// pattern (QNetworkAccessManager is already async).
//
// httpCode in the result signals:
//   200 / 202  -> request succeeded
//   400 / 401 / 404 / 409 / 503  -> daemon was reachable but rejected
//   -1         -> Pi unreachable (DNS / connection refused / timeout)
//   other      -> raw HTTP status code

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

class QNetworkAccessManager;
class QNetworkReply;

class PiControlClient : public QObject
{
    Q_OBJECT
public:
    explicit PiControlClient(const QString &host, quint16 port,
                             const QString &token = {},
                             QObject *parent = nullptr);

    QString host() const { return m_host; }
    quint16 port() const { return m_port; }

    // Runtime-mutable host/port/token (so the user can re-target the
    // daemon from the dock UI without restarting). Changes take effect
    // on the next request.
    void setHost(const QString &h)  { m_host  = h; }
    void setPort(quint16 p)         { m_port  = p; }
    void setToken(const QString &t) { m_token = t; }

    // Drop+recreate the QNetworkAccessManager. Clears Qt's internal DNS
    // cache, drops pooled connections, and abandons any in-flight reply.
    // The next request starts from a clean slate -- useful after WiFi
    // roaming or a DNS/proxy change confuses the resolver.
    void reconnect();

public slots:
    // Fire-and-forget; result comes back on the matching signal.
    void fetchHealthz();
    void fetchStatus();
    void fetchOptions();
    void fetchChannels();
    void sendControl(const QJsonObject &patch);
    void sendImpedance(int durationSec);

signals:
    void healthzReceived(int httpCode, QJsonObject payload);
    void statusReceived(int httpCode, QJsonObject payload);
    void optionsReceived(int httpCode, QJsonObject payload);
    // Convenience: payload["channels"] flattened into a string list (or
    // empty on error). Raw payload also available if the consumer wants.
    void channelsReceived(int httpCode, QStringList channels,
                          QJsonObject payload);
    void controlResult(int httpCode, QJsonObject payload);
    void impedanceResult(int httpCode, QJsonObject payload);

private:
    enum class Verb { Get, Post };
    // Helper: build + send a request, route reply to the given signal.
    void send(Verb verb, const QString &path, const QJsonObject &body,
              const char *signalKey);

    QNetworkAccessManager *m_nam = nullptr;
    QString m_host;
    quint16 m_port = 0;
    QString m_token;
    int m_timeoutMs = 4000;     // mirrors the 4 s timeout in pi_control.py
};
