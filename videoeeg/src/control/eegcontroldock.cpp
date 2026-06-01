#include "eegcontroldock.h"

#include "picontrolclient.h"
#include "picontrolpoller.h"

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
#include <QRegularExpression>
#include <QSettings>
#include <QSpinBox>
#include <QToolButton>
#include <QVBoxLayout>

EegControlDock::EegControlDock(PiControlPoller *poller, QWidget *parent)
    : QDockWidget(parent), m_poller(poller)
{
    setWindowTitle(tr("EEG Pi control"));
    setAllowedAreas(Qt::LeftDockWidgetArea | Qt::RightDockWidgetArea);

    auto *root = new QWidget(this);
    m_box = new QGroupBox(root);
    updateGroupTitle();
    auto *form = new QFormLayout(m_box);

    // --- widgets ---
    m_mode = new QComboBox;
    m_mode->addItems({QStringLiteral("eeg"),
                      QStringLiteral("impedance"),
                      QStringLiteral("stopped")});

    m_rate = new QComboBox;
    // sane defaults; will be overwritten from /options on first poll
    for (int r : {500, 1000, 2000, 4000, 8000, 16000})
        m_rate->addItem(QString::number(r));

    m_channels = new QLineEdit;
    m_channels->setPlaceholderText(tr("blank = all; e.g. ExG_1, ExG_2"));

    m_apply = new QPushButton(tr("Apply"));
    connect(m_apply, &QPushButton::clicked,
            this, &EegControlDock::onApplyClicked);

    m_impDur = new QSpinBox;
    m_impDur->setRange(5, 600);
    m_impDur->setValue(45);
    m_impDur->setSuffix(QStringLiteral(" s"));

    m_impBtn = new QPushButton(tr("Impedance check"));
    connect(m_impBtn, &QPushButton::clicked,
            this, &EegControlDock::onImpedanceClicked);

    // --- connection-management buttons ---
    m_reconnect = new QToolButton;
    m_reconnect->setText(QStringLiteral("↻"));
    m_reconnect->setToolTip(tr("Reconnect now (flushes DNS cache)"));
    m_reconnect->setAutoRaise(true);
    connect(m_reconnect, &QToolButton::clicked,
            this, &EegControlDock::onReconnectClicked);

    m_editHost = new QToolButton;
    m_editHost->setText(QStringLiteral("…"));
    m_editHost->setToolTip(tr("Edit host:port"));
    m_editHost->setAutoRaise(true);
    connect(m_editHost, &QToolButton::clicked,
            this, &EegControlDock::onEditHostClicked);

    m_status = new QLabel(tr("control: connecting…"));
    m_status->setWordWrap(true);
    m_status->setStyleSheet(QStringLiteral("font-family: Consolas, monospace;"));

    m_result = new QLabel;
    m_result->setWordWrap(true);

    // --- layout ---
    form->addRow(tr("Mode"), m_mode);
    form->addRow(tr("Rate (Hz)"), m_rate);
    form->addRow(tr("Channels"), m_channels);
    form->addRow(m_apply);

    auto *imp = new QHBoxLayout;
    imp->addWidget(m_impDur);
    imp->addWidget(m_impBtn);
    auto *impWrap = new QWidget;
    impWrap->setLayout(imp);
    form->addRow(tr("Impedance"), impWrap);

    // Status line + reconnect / edit-host buttons on the right.
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
            this, &EegControlDock::refreshFromPoller);
    connect(m_poller, &PiControlPoller::controlResult,
            this, &EegControlDock::onControlResult);
    connect(m_poller, &PiControlPoller::impedanceResult,
            this, &EegControlDock::onImpedanceResult);
}

// --------------------------------------------------------------------------
// One-time population of combos from /options
// --------------------------------------------------------------------------

void EegControlDock::applyOptionsOnce()
{
    if (m_optsApplied)
        return;
    const QJsonObject opts = m_poller->options();
    if (opts.isEmpty())
        return;

    if (const QJsonValue v = opts.value(QStringLiteral("rates")); v.isArray()) {
        const QString cur = m_rate->currentText();
        m_rate->clear();
        for (const QJsonValue &x : v.toArray())
            m_rate->addItem(QString::number(x.toInt()));
        const int idx = m_rate->findText(cur);
        if (idx >= 0)
            m_rate->setCurrentIndex(idx);
    }

    if (const QJsonValue v = opts.value(QStringLiteral("modes")); v.isArray()) {
        m_mode->clear();
        for (const QJsonValue &x : v.toArray())
            m_mode->addItem(x.toString());
    }

    m_optsApplied = true;
}

// --------------------------------------------------------------------------
// Snapshot -> UI (status line, busy-disable Apply)
// --------------------------------------------------------------------------

void EegControlDock::refreshFromPoller()
{
    applyOptionsOnce();

    const QStringList chans = m_poller->channels();
    if (!chans.isEmpty())
        m_channels->setToolTip(tr("available: %1").arg(chans.join(", ")));

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

    const QString mode = ds.value(QStringLiteral("mode")).toString();
    const int rate     = ds.value(QStringLiteral("rate")).toInt();
    const QJsonValue chVal = ds.value(QStringLiteral("channels"));
    const QString chSummary = (chVal.isNull() || chVal.toArray().isEmpty())
            ? QStringLiteral("all")
            : QString::number(chVal.toArray().size());
    const bool alive = st.value(QStringLiteral("child_alive")).toBool();
    const QString amp = st.value(QStringLiteral("amp_detected")).toString();
    const QString lastErr = st.value(QStringLiteral("last_error")).toString();

    QString line = tr("control: mode=%1 rate=%2 ch=%3  child=%4 amp=%5")
                       .arg(mode)
                       .arg(rate)
                       .arg(chSummary)
                       .arg(alive ? QStringLiteral("UP") : QStringLiteral("down"))
                       .arg(amp.isEmpty() ? QStringLiteral("?") : amp);
    if (busy)    line += QStringLiteral("  [APPLYING]");
    // Note: `last_error` is just the most recent stderr line from the
    // streamer; it often contains benign INFO messages from liblsl. Truncate
    // and prefix as "last:" rather than "ERR:" so it doesn't look alarming.
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

void EegControlDock::onApplyClicked()
{
    QJsonObject patch;
    patch.insert(QStringLiteral("mode"), m_mode->currentText());
    patch.insert(QStringLiteral("rate"), m_rate->currentText().toInt());

    const QString txt = m_channels->text().trimmed();
    if (txt.isEmpty()) {
        patch.insert(QStringLiteral("channels"), QJsonValue::Null);
    } else {
        QJsonArray arr;
        for (const QString &c : txt.split(QRegularExpression(QStringLiteral("[,;\\s]+")),
                                          Qt::SkipEmptyParts))
            arr.append(c);
        patch.insert(QStringLiteral("channels"), arr);
    }

    m_apply->setEnabled(false);
    m_result->setText(tr("applying…"));
    m_poller->sendControl(patch);
}

void EegControlDock::onImpedanceClicked()
{
    m_impBtn->setEnabled(false);
    m_result->setText(tr("impedance starting…"));
    m_poller->sendImpedance(m_impDur->value());
}

// --------------------------------------------------------------------------
// Connection management
// --------------------------------------------------------------------------

void EegControlDock::updateGroupTitle()
{
    if (!m_box) return;
    m_box->setTitle(tr("Perun32 EEG  (%1:%2)")
                        .arg(m_poller->client()->host())
                        .arg(m_poller->client()->port()));
}

void EegControlDock::onReconnectClicked()
{
    m_result->setText(tr("reconnecting…"));
    m_poller->reconnect();
}

void EegControlDock::onEditHostClicked()
{
    auto *client = m_poller->client();
    const QString current = QStringLiteral("%1:%2")
                                .arg(client->host())
                                .arg(client->port());
    bool ok = false;
    const QString text = QInputDialog::getText(
        this, tr("EEG Pi host"),
        tr("host:port  (e.g. camera-pi.local:8080 or 192.168.1.42:8080)"),
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
    s.beginGroup(QStringLiteral("eegControl"));
    s.setValue(QStringLiteral("host"), h);
    s.setValue(QStringLiteral("port"), p);
    s.endGroup();

    m_optsApplied = false;     // re-fetch on next poll (host might differ)
    m_result->setText(tr("host updated; reconnecting…"));
    m_poller->reconnect();
}

// --------------------------------------------------------------------------
// Command results
// --------------------------------------------------------------------------

static QString resultLine(const QString &tag, int code,
                          const QJsonObject &payload)
{
    if (code == -1)
        return QStringLiteral("%1: unreachable (%2)").arg(tag,
            payload.value(QStringLiteral("error")).toString(QStringLiteral("?")));
    if (code == 200 || code == 202)
        return QStringLiteral("%1: OK").arg(tag);
    return QStringLiteral("%1: error %2 — %3").arg(tag).arg(code)
        .arg(payload.value(QStringLiteral("error")).toString());
}

void EegControlDock::onControlResult(int code, QJsonObject payload)
{
    m_result->setText(resultLine(QStringLiteral("control"), code, payload));
    m_apply->setEnabled(true);
}

void EegControlDock::onImpedanceResult(int code, QJsonObject payload)
{
    m_result->setText(resultLine(QStringLiteral("impedance"), code, payload));
    m_impBtn->setEnabled(true);
}
