#include "videocontroldock.h"

#include "picontrolclient.h"
#include "picontrolpoller.h"

#include <QCheckBox>
#include <QComboBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QToolButton>
#include <QVBoxLayout>

VideoControlDock::VideoControlDock(PiControlPoller *poller, QWidget *parent)
    : QDockWidget(parent), m_poller(poller)
{
    setWindowTitle(tr("Video Pi control"));
    setAllowedAreas(Qt::LeftDockWidgetArea | Qt::RightDockWidgetArea);

    auto *root = new QWidget(this);
    m_box = new QGroupBox(root);
    updateGroupTitle();
    auto *form = new QFormLayout(m_box);

    // --- widgets ---
    m_mode = new QComboBox;
    m_mode->addItems({QStringLiteral("video"), QStringLiteral("stopped")});

    m_w = new QSpinBox;
    m_w->setRange(160, 1920);
    m_w->setValue(960);

    m_h = new QSpinBox;
    m_h->setRange(120, 1080);
    m_h->setValue(720);

    m_fps = new QSpinBox;
    m_fps->setRange(1, 60);
    m_fps->setValue(30);

    m_br = new QSpinBox;
    m_br->setRange(100, 20000);
    m_br->setValue(4000);
    m_br->setSuffix(QStringLiteral(" kbps"));

    m_hflip = new QCheckBox(tr("hflip"));
    m_vflip = new QCheckBox(tr("vflip"));

    m_apply = new QPushButton(tr("Apply"));
    connect(m_apply, &QPushButton::clicked,
            this, &VideoControlDock::onApplyClicked);

    m_reconnect = new QToolButton;
    m_reconnect->setText(QStringLiteral("↻"));
    m_reconnect->setToolTip(tr("Reconnect now (flushes DNS cache)"));
    m_reconnect->setAutoRaise(true);
    connect(m_reconnect, &QToolButton::clicked,
            this, &VideoControlDock::onReconnectClicked);

    m_editHost = new QToolButton;
    m_editHost->setText(QStringLiteral("…"));
    m_editHost->setToolTip(tr("Edit host:port"));
    m_editHost->setAutoRaise(true);
    connect(m_editHost, &QToolButton::clicked,
            this, &VideoControlDock::onEditHostClicked);

    m_status = new QLabel(tr("control: connecting…"));
    m_status->setWordWrap(true);
    m_status->setStyleSheet(QStringLiteral("font-family: Consolas, monospace;"));

    m_result = new QLabel;
    m_result->setWordWrap(true);

    // --- layout ---
    auto *wh = new QHBoxLayout;
    wh->addWidget(m_w);
    wh->addWidget(new QLabel(QStringLiteral("×")));
    wh->addWidget(m_h);
    auto *whWrap = new QWidget;
    whWrap->setLayout(wh);

    auto *fl = new QHBoxLayout;
    fl->addWidget(m_hflip);
    fl->addWidget(m_vflip);
    auto *flWrap = new QWidget;
    flWrap->setLayout(fl);

    form->addRow(tr("Mode"), m_mode);
    form->addRow(tr("Size"), whWrap);
    form->addRow(tr("FPS"), m_fps);
    form->addRow(tr("Bitrate"), m_br);
    form->addRow(tr("Flip"), flWrap);
    form->addRow(m_apply);

    // status + connection-management buttons on one row
    auto *statusRow = new QHBoxLayout;
    statusRow->setSpacing(4);
    statusRow->addWidget(m_status, 1);
    statusRow->addWidget(m_reconnect);
    statusRow->addWidget(m_editHost);
    auto *statusWrap = new QWidget;
    statusWrap->setLayout(statusRow);
    form->addRow(statusWrap);
    form->addRow(m_result);

    auto *rootLay = new QVBoxLayout(root);
    rootLay->setContentsMargins(8, 8, 8, 8);
    rootLay->addWidget(m_box);
    rootLay->addStretch(1);
    setWidget(root);

    // --- wiring ---
    connect(m_poller, &PiControlPoller::snapshotChanged,
            this, &VideoControlDock::refreshFromPoller);
    connect(m_poller, &PiControlPoller::controlResult,
            this, &VideoControlDock::onControlResult);
}

// --------------------------------------------------------------------------
// One-time population from /options (W/H/fps/bitrate ranges, modes)
// --------------------------------------------------------------------------

void VideoControlDock::applyOptionsOnce()
{
    if (m_optsApplied)
        return;
    const QJsonObject opts = m_poller->options();
    if (opts.isEmpty())
        return;

    const QJsonObject ranges = opts.value(QStringLiteral("ranges")).toObject();
    auto applyRange = [&ranges](const char *key, QSpinBox *sb, int scale = 1) {
        const QJsonArray arr = ranges.value(QString::fromLatin1(key)).toArray();
        if (arr.size() == 2)
            sb->setRange(arr.at(0).toInt() / scale, arr.at(1).toInt() / scale);
    };
    applyRange("width",   m_w);
    applyRange("height",  m_h);
    applyRange("fps",     m_fps);
    applyRange("bitrate", m_br, 1000);    // daemon uses bps; UI uses kbps

    if (const QJsonValue v = opts.value(QStringLiteral("modes")); v.isArray()) {
        m_mode->clear();
        for (const QJsonValue &x : v.toArray())
            m_mode->addItem(x.toString());
    }

    m_optsApplied = true;
}

// --------------------------------------------------------------------------
// Snapshot -> UI
// --------------------------------------------------------------------------

void VideoControlDock::refreshFromPoller()
{
    applyOptionsOnce();

    if (!m_poller->confirmed()) {
        m_status->setText(tr("control: connecting…"));
        return;
    }
    if (!m_poller->reachable()) {
        m_status->setText(tr("control: Pi unreachable (%1)  — ↻ to retry")
                              .arg(m_poller->client()->host()));
        return;
    }
    if (!m_poller->daemonUp()) {
        m_status->setText(tr("control: Pi up, daemon DOWN (break-glass?)"));
        return;
    }

    const QJsonObject st = m_poller->status();
    const QJsonObject ds = st.value(QStringLiteral("state")).toObject();
    const bool busy = st.value(QStringLiteral("transition_in_progress")).toBool();
    m_apply->setEnabled(!busy);

    const int bitrateBps = ds.value(QStringLiteral("bitrate")).toInt();
    const QString lastErr = st.value(QStringLiteral("last_error")).toString();

    QString line = tr("control: mode=%1 %2x%3@%4 %5kbps  child=%6")
        .arg(ds.value(QStringLiteral("mode")).toString())
        .arg(ds.value(QStringLiteral("width")).toInt())
        .arg(ds.value(QStringLiteral("height")).toInt())
        .arg(ds.value(QStringLiteral("fps")).toInt())
        .arg(bitrateBps / 1000)
        .arg(st.value(QStringLiteral("child_alive")).toBool()
                 ? QStringLiteral("UP") : QStringLiteral("down"));
    if (busy)    line += QStringLiteral("  [APPLYING]");
    if (!lastErr.isEmpty()) {
        QString trimmed = lastErr.trimmed();
        if (trimmed.size() > 80) trimmed = trimmed.left(77) + QStringLiteral("…");
        line += QStringLiteral("  last:%1").arg(trimmed);
    }
    m_status->setText(line);
}

// --------------------------------------------------------------------------
// User actions
// --------------------------------------------------------------------------

void VideoControlDock::onApplyClicked()
{
    QJsonObject patch;
    patch.insert(QStringLiteral("mode"),    m_mode->currentText());
    patch.insert(QStringLiteral("width"),   m_w->value());
    patch.insert(QStringLiteral("height"),  m_h->value());
    patch.insert(QStringLiteral("fps"),     m_fps->value());
    patch.insert(QStringLiteral("bitrate"), m_br->value() * 1000);   // -> bps
    patch.insert(QStringLiteral("hflip"),   m_hflip->isChecked());
    patch.insert(QStringLiteral("vflip"),   m_vflip->isChecked());

    m_apply->setEnabled(false);
    m_result->setText(tr("applying…"));
    m_poller->sendControl(patch);
}

// --------------------------------------------------------------------------
// Command result
// --------------------------------------------------------------------------

// --------------------------------------------------------------------------
// Connection management
// --------------------------------------------------------------------------

void VideoControlDock::updateGroupTitle()
{
    if (!m_box) return;
    m_box->setTitle(tr("Pi Camera  (%1:%2)")
                        .arg(m_poller->client()->host())
                        .arg(m_poller->client()->port()));
}

void VideoControlDock::onReconnectClicked()
{
    m_result->setText(tr("reconnecting…"));
    m_poller->reconnect();
}

void VideoControlDock::onEditHostClicked()
{
    auto *client = m_poller->client();
    const QString current = QStringLiteral("%1:%2")
                                .arg(client->host())
                                .arg(client->port());
    bool ok = false;
    const QString text = QInputDialog::getText(
        this, tr("Video Pi host"),
        tr("host:port  (e.g. video-pi.local:8081 or 192.168.1.43:8081)"),
        QLineEdit::Normal, current, &ok);
    if (!ok) return;
    const QString trimmed = text.trimmed();
    if (trimmed.isEmpty()) return;
    const int colon = trimmed.lastIndexOf(QLatin1Char(':'));
    if (colon <= 0 || colon >= trimmed.size() - 1) {
        m_result->setText(tr("edit: bad format (need host:port)"));
        return;
    }
    const QString h = trimmed.left(colon).trimmed();
    bool portOk = false;
    const uint p = trimmed.mid(colon + 1).trimmed().toUInt(&portOk);
    if (!portOk || p == 0 || p > 65535 || h.isEmpty()) {
        m_result->setText(tr("edit: bad host or port"));
        return;
    }
    client->setHost(h);
    client->setPort(static_cast<quint16>(p));
    updateGroupTitle();

    QSettings s;
    s.beginGroup(QStringLiteral("videoControl"));
    s.setValue(QStringLiteral("host"), h);
    s.setValue(QStringLiteral("port"), p);
    s.endGroup();

    m_optsApplied = false;
    m_result->setText(tr("host updated; reconnecting…"));
    m_poller->reconnect();
}

void VideoControlDock::onControlResult(int code, QJsonObject payload)
{
    QString msg;
    if (code == -1)
        msg = QStringLiteral("video-control: unreachable (%1)").arg(
            payload.value(QStringLiteral("error"))
                   .toString(QStringLiteral("?")));
    else if (code == 200 || code == 202)
        msg = QStringLiteral("video-control: OK");
    else
        msg = QStringLiteral("video-control: error %1 — %2").arg(code).arg(
            payload.value(QStringLiteral("error")).toString());
    m_result->setText(msg);
    m_apply->setEnabled(true);
}
