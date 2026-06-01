#include "picontrolclient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

PiControlClient::PiControlClient(const QString &host, quint16 port,
                                 const QString &token, QObject *parent)
    : QObject(parent), m_host(host), m_port(port), m_token(token)
{
    m_nam = new QNetworkAccessManager(this);
    // Skip Windows WPAD proxy auto-detection. The Pi daemons are on a flat
    // LAN; without this, the first HTTP request can stall the UI for several
    // seconds on Windows ("program not responding") while Qt probes for a
    // proxy that does not exist.
    m_nam->setProxy(QNetworkProxy::NoProxy);
}

void PiControlClient::reconnect()
{
    // Pending replies are children of m_nam and get deleted with it; their
    // finished() signals never fire, which is what we want (we discard
    // stale results during a forced reconnect).
    delete m_nam;
    m_nam = new QNetworkAccessManager(this);
    m_nam->setProxy(QNetworkProxy::NoProxy);
}

// --------------------------------------------------------------------------
// Public slots
// --------------------------------------------------------------------------

void PiControlClient::fetchHealthz()
{
    send(Verb::Get, QStringLiteral("/healthz"), {}, "healthzReceived");
}

void PiControlClient::fetchStatus()
{
    send(Verb::Get, QStringLiteral("/status"), {}, "statusReceived");
}

void PiControlClient::fetchOptions()
{
    send(Verb::Get, QStringLiteral("/options"), {}, "optionsReceived");
}

void PiControlClient::fetchChannels()
{
    send(Verb::Get, QStringLiteral("/channels"), {}, "channelsReceived");
}

void PiControlClient::sendControl(const QJsonObject &patch)
{
    send(Verb::Post, QStringLiteral("/control"), patch, "controlResult");
}

void PiControlClient::sendImpedance(int durationSec)
{
    QJsonObject body;
    body.insert(QStringLiteral("duration"), durationSec);
    send(Verb::Post, QStringLiteral("/impedance"), body, "impedanceResult");
}

// --------------------------------------------------------------------------
// Internal
// --------------------------------------------------------------------------

void PiControlClient::send(Verb verb, const QString &path,
                           const QJsonObject &body, const char *signalKey)
{
    QUrl url;
    url.setScheme(QStringLiteral("http"));
    url.setHost(m_host);
    url.setPort(m_port);
    url.setPath(path);

    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader,
                  QStringLiteral("application/json"));
    req.setTransferTimeout(m_timeoutMs);     // Qt 5.15+ / Qt 6
    if (!m_token.isEmpty())
        req.setRawHeader("X-Control-Token", m_token.toUtf8());

    QNetworkReply *reply = nullptr;
    if (verb == Verb::Get) {
        reply = m_nam->get(req);
    } else {
        const QByteArray payload = QJsonDocument(body).toJson(
            QJsonDocument::Compact);
        reply = m_nam->post(req, payload);
    }

    // QString key for the lambda (the `const char*` may dangle later).
    const QString key = QString::fromLatin1(signalKey);

    connect(reply, &QNetworkReply::finished, this, [this, reply, key]() {
        const int httpCode = reply->attribute(
            QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray raw = reply->readAll();
        const QNetworkReply::NetworkError err = reply->error();

        // Parse JSON if we got any (daemon always returns JSON, even errors).
        QJsonObject payload;
        if (!raw.isEmpty()) {
            QJsonParseError pe{};
            const QJsonDocument doc = QJsonDocument::fromJson(raw, &pe);
            if (pe.error == QJsonParseError::NoError && doc.isObject())
                payload = doc.object();
            else
                payload.insert(QStringLiteral("error"),
                               QString::fromUtf8(raw));
        }

        // httpCode == 0 means we never got a response (DNS/timeout/refused).
        const int code = (httpCode > 0) ? httpCode
                                        : (err == QNetworkReply::NoError
                                               ? 200 : -1);
        if (code == -1 && !payload.contains(QStringLiteral("error")))
            payload.insert(QStringLiteral("error"), reply->errorString());

        // Route to the right signal.
        if (key == QLatin1String("healthzReceived"))
            emit healthzReceived(code, payload);
        else if (key == QLatin1String("statusReceived"))
            emit statusReceived(code, payload);
        else if (key == QLatin1String("optionsReceived"))
            emit optionsReceived(code, payload);
        else if (key == QLatin1String("channelsReceived")) {
            QStringList chans;
            const QJsonValue v = payload.value(QStringLiteral("channels"));
            if (v.isArray())
                for (const QJsonValue &x : v.toArray())
                    chans << x.toString();
            emit channelsReceived(code, chans, payload);
        } else if (key == QLatin1String("controlResult"))
            emit controlResult(code, payload);
        else if (key == QLatin1String("impedanceResult"))
            emit impedanceResult(code, payload);

        reply->deleteLater();
    });
}
