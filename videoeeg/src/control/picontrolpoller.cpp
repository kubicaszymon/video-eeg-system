#include "picontrolpoller.h"

#include "picontrolclient.h"

#include <QTimer>

PiControlPoller::PiControlPoller(PiControlClient *client, QObject *parent)
    : QObject(parent), m_client(client)
{
    m_timer = new QTimer(this);
    connect(m_timer, &QTimer::timeout, this, &PiControlPoller::onTick);

    connect(m_client, &PiControlClient::statusReceived,
            this, &PiControlPoller::onStatus);
    connect(m_client, &PiControlClient::optionsReceived,
            this, &PiControlPoller::onOptions);
    connect(m_client, &PiControlClient::channelsReceived,
            this, &PiControlPoller::onChannels);

    // Re-emit command results so the UI binds to the poller, not the client.
    connect(m_client, &PiControlClient::controlResult,
            this, &PiControlPoller::controlResult);
    connect(m_client, &PiControlClient::impedanceResult,
            this, &PiControlPoller::impedanceResult);
}

void PiControlPoller::start(int periodMs)
{
    // Start the periodic tick. We deliberately do NOT call onTick() here:
    // firing the first batch of HTTP requests synchronously inside the
    // MainWindow constructor was stalling the UI message pump on Windows
    // for a few seconds while WinSock / mDNS warmed up. The first tick now
    // happens periodMs later -- still fast (~1 s), and the GUI is already
    // visible by then so any short stall is invisible.
    m_metaCountdown = 0;
    m_timer->start(periodMs);
}

void PiControlPoller::stop()
{
    m_timer->stop();
}

void PiControlPoller::sendControl(const QJsonObject &patch)
{
    if (m_client) m_client->sendControl(patch);
}

void PiControlPoller::sendImpedance(int durationSec)
{
    if (m_client) m_client->sendImpedance(durationSec);
}

// --------------------------------------------------------------------------
// Periodic work
// --------------------------------------------------------------------------

void PiControlPoller::onTick()
{
    m_client->fetchStatus();

    // Refresh slow-changing meta less often.
    if (m_metaCountdown <= 0) {
        m_client->fetchOptions();
        m_client->fetchChannels();
        m_metaCountdown = m_metaEvery;
    } else {
        --m_metaCountdown;
    }
}

void PiControlPoller::onStatus(int code, QJsonObject payload)
{
    const bool requestSucceeded = (code != -1);
    const bool daemonUp         = (code == 200);
    bool changed = false;

    if (requestSucceeded) {
        // Any answer from the network (200, 4xx, 5xx) clears the failure
        // counter -- we definitely reached the host.
        m_consecFailures = 0;
        if (!m_uiConfirmed) { m_uiConfirmed = true; changed = true; }
        if (!m_reachable)   { m_reachable   = true; changed = true; }
        if (daemonUp != m_daemonUp) { m_daemonUp = daemonUp; changed = true; }
        if (daemonUp && payload != m_status) {
            m_status = payload;
            changed = true;
        }
    } else {
        // Failed poll. Don't flip the UI yet -- a single timeout (mDNS
        // race, transient WiFi blip) shouldn't yell "unreachable". Wait
        // for the threshold.
        ++m_consecFailures;
        if (m_consecFailures >= kFailureThreshold) {
            if (!m_uiConfirmed) { m_uiConfirmed = true;  changed = true; }
            if (m_reachable)    { m_reachable   = false; changed = true; }
            if (m_daemonUp)     { m_daemonUp    = false; changed = true; }
        }
    }
    if (changed)
        emit snapshotChanged();
}

void PiControlPoller::reconnect()
{
    // Clean slate: drop the Qt network manager (DNS + conn cache go with
    // it) and reset our local debounce state. UI flips to "connecting…"
    // until the next response.
    m_client->reconnect();
    m_consecFailures = 0;
    m_uiConfirmed = false;
    m_reachable   = false;
    m_daemonUp    = false;
    m_metaCountdown = 0;
    emit snapshotChanged();
    onTick();           // poll now, don't wait a full period
}

void PiControlPoller::onOptions(int code, QJsonObject payload)
{
    if (code == 200 && payload != m_options) {
        m_options = payload;
        emit snapshotChanged();
    }
}

void PiControlPoller::onChannels(int code, QStringList channels,
                                 QJsonObject /*payload*/)
{
    if (code == 200 && channels != m_channels) {
        m_channels = channels;
        emit snapshotChanged();
    }
}
