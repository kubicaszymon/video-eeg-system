#include "monitorview.h"
#include "canvases.h"
#include "format.h"
#include "theme.h"
#include "uihelpers.h"
#include "videodock.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QTimer>
#include <QVBoxLayout>

namespace {

QString numStr(double v)
{
    QString s = QString::number(v, 'g', 6);
    return s;
}

QWidget *buildField(const QString &label, const QString &value,
                     bool mono, bool mute)
{
    auto *w = new QWidget;
    w->setStyleSheet(QStringLiteral("border-bottom:1px solid %1;")
                         .arg(theme::hex(theme::BorderSub)));
    auto *v = new QVBoxLayout(w);
    v->setContentsMargins(0, 7, 0, 7);
    v->setSpacing(2);

    auto *l = new QLabel(label);
    {
        QFont f = l->font();
        f.setPixelSize(11);
        l->setFont(f);
        l->setStyleSheet(QStringLiteral("color:%1; border:none;")
                             .arg(theme::hex(theme::Muted)));
    }
    auto *val = new QLabel(value);
    val->setWordWrap(true);
    {
        QFont f = mono ? QFont(theme::monoFontFamily()) : val->font();
        f.setPixelSize(13);
        val->setFont(f);
        val->setStyleSheet(QStringLiteral("color:%1; border:none;")
                               .arg(theme::hex(mute ? theme::Dim : theme::Text)));
    }
    v->addWidget(l);
    v->addWidget(val);
    return w;
}

QWidget *buildDeviceRow(const QString &label, QLabel **valueOut)
{
    auto *w = new QWidget;
    w->setStyleSheet(QStringLiteral("border-bottom:1px solid %1;")
                         .arg(theme::hex(theme::BorderSub)));
    auto *row = new QHBoxLayout(w);
    row->setContentsMargins(0, 6, 0, 6);
    row->setSpacing(9);

    auto *d = new QLabel;
    d->setFixedSize(6, 6);
    d->setStyleSheet(QStringLiteral("background:%1; border-radius:3px;")
                         .arg(theme::hex(theme::Accent)));
    row->addWidget(d, 0, Qt::AlignVCenter);

    auto *col = new QVBoxLayout;
    col->setContentsMargins(0, 0, 0, 0);
    col->setSpacing(1);
    auto *cap = new QLabel(label);
    {
        QFont f = cap->font();
        f.setPixelSize(11);
        cap->setFont(f);
        cap->setStyleSheet(QStringLiteral("color:%1; border:none;")
                               .arg(theme::hex(theme::Muted)));
    }
    auto *val = new QLabel;
    val->setWordWrap(true);
    {
        QFont f(theme::monoFontFamily());
        f.setPixelSize(11);
        val->setFont(f);
        val->setStyleSheet(QStringLiteral("border:none;"));
    }
    col->addWidget(cap);
    col->addWidget(val);
    row->addLayout(col, 1);
    *valueOut = val;
    return w;
}

} // namespace

// ================================ Sidebar =================================

Sidebar::Sidebar(QWidget *parent) : QWidget(parent)
{
    setFixedWidth(theme::SidebarWidth);
    setStyleSheet(QStringLiteral(
        "background:%1; border-right:1px solid %2;")
        .arg(theme::hex(theme::Panel), theme::hex(theme::Border)));

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    auto *scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    outer->addWidget(scroll);

    auto *content = new QWidget;
    content->setStyleSheet(QStringLiteral("background:transparent;"));
    scroll->setWidget(content);

    auto *v = new QVBoxLayout(content);
    v->setContentsMargins(18, 22, 18, 22);
    v->setSpacing(22);

    // brand
    auto *brand = new QHBoxLayout;
    brand->setSpacing(10);
    auto *mark = new QLabel(QStringLiteral("ψ"));
    mark->setFixedSize(28, 28);
    mark->setAlignment(Qt::AlignCenter);
    mark->setStyleSheet(QStringLiteral(
        "background:%1; color:%2; border-radius:6px;"
        "font-weight:700; font-size:14px;")
        .arg(theme::hex(theme::Accent), theme::hex(theme::Bg)));
    brand->addWidget(mark, 0, Qt::AlignVCenter);
    auto *bcol = new QVBoxLayout;
    bcol->setSpacing(1);
    auto *bn = new QLabel(QStringLiteral("NeuroSync"));
    {
        QFont f = bn->font();
        f.setPixelSize(13);
        f.setWeight(QFont::DemiBold);
        bn->setFont(f);
    }
    auto *bs = new QLabel(QStringLiteral("VEEG · v0.1 research"));
    {
        QFont f = bs->font();
        f.setPixelSize(11);
        bs->setFont(f);
        bs->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    }
    bcol->addWidget(bn);
    bcol->addWidget(bs);
    brand->addLayout(bcol, 1);
    v->addLayout(brand);

    // session section
    auto *sessWrap = new QVBoxLayout;
    sessWrap->setSpacing(8);
    sessWrap->addWidget(ui::sectionCaption(QStringLiteral("Session")));
    auto *sessHost = new QWidget;
    m_sessionBox = new QVBoxLayout(sessHost);
    m_sessionBox->setContentsMargins(0, 0, 0, 0);
    m_sessionBox->setSpacing(0);
    sessWrap->addWidget(sessHost);
    v->addLayout(sessWrap);

    // device section
    auto *devWrap = new QVBoxLayout;
    devWrap->setSpacing(8);
    devWrap->addWidget(ui::sectionCaption(QStringLiteral("Device")));
    devWrap->addWidget(buildDeviceRow(QStringLiteral("Amplifier"), &m_ampVal));
    devWrap->addWidget(buildDeviceRow(QStringLiteral("Camera"), &m_camVal));
    devWrap->addWidget(buildDeviceRow(QStringLiteral("Storage"), &m_stoVal));
    devWrap->addWidget(buildDeviceRow(QStringLiteral("Filters"), &m_filVal));
    v->addLayout(devWrap);

    // markers section
    m_markerSection = new QWidget;
    auto *mk = new QVBoxLayout(m_markerSection);
    mk->setContentsMargins(0, 0, 0, 0);
    mk->setSpacing(8);
    auto *mkHead = new QHBoxLayout;
    mkHead->addWidget(ui::sectionCaption(QStringLiteral("Markers")), 1);
    m_markerCount = new QLabel(QStringLiteral("0"));
    {
        QFont f = m_markerCount->font();
        f.setPixelSize(11);
        m_markerCount->setFont(f);
        m_markerCount->setStyleSheet(
            QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    }
    mkHead->addWidget(m_markerCount, 0, Qt::AlignRight | Qt::AlignVCenter);
    mk->addLayout(mkHead);

    auto *listHost = new QWidget;
    m_markerList = new QVBoxLayout(listHost);
    m_markerList->setContentsMargins(0, 0, 0, 0);
    m_markerList->setSpacing(1);
    mk->addWidget(listHost);

    auto *addBtn = new QPushButton(QStringLiteral("+ Add marker"));
    addBtn->setCursor(Qt::PointingHandCursor);
    addBtn->setMinimumHeight(34);
    addBtn->setStyleSheet(QStringLiteral(
        "QPushButton{background:transparent; color:%1;"
        "border:1px dashed %2; border-radius:6px; font-weight:600;"
        "font-size:12px;} QPushButton:hover{background:%3;}")
        .arg(theme::hex(theme::Accent), theme::hex(theme::AccentDim),
             theme::hex(theme::TraceArea)));
    connect(addBtn, &QPushButton::clicked, this,
            &Sidebar::addMarkerRequested);
    mk->addWidget(addBtn);

    v->addWidget(m_markerSection);
    v->addStretch(1);

    rebuildSession();
    setDevices(m_devices);
    setFilters(m_filters);
    m_markerSection->setVisible(false);
}

void Sidebar::setRecording(bool on)
{
    m_recording = on;
    m_markerSection->setVisible(on);
    rebuildSession();
}

void Sidebar::setSession(const Session &s, bool hasSession)
{
    m_session = s;
    m_hasSession = hasSession;
    rebuildSession();
}

void Sidebar::setDevices(const Devices &d)
{
    m_devices = d;
    m_ampVal->setText(d.amp.label + QStringLiteral(" · ") + d.amp.sub);
    m_camVal->setText(d.camera.label + QStringLiteral(" · ") + d.camera.sub);
    m_stoVal->setText(d.storage.label);
}

void Sidebar::setFilters(const Filters &f)
{
    m_filters = f;
    QString t = QStringLiteral("HP %1 · LP %2")
                    .arg(numStr(f.hp), numStr(f.lp));
    if (f.notch != 0.0)
        t += QStringLiteral(" · Notch ") + numStr(f.notch);
    m_filVal->setText(t);
}

void Sidebar::setMarkers(const QVector<Marker> &m)
{
    m_markers = m;
    rebuildMarkers();
}

void Sidebar::rebuildSession()
{
    QLayoutItem *it;
    while ((it = m_sessionBox->takeAt(0))) {
        if (it->widget())
            it->widget()->deleteLater();
        delete it;
    }
    if (!m_hasSession) {
        auto *none = new QLabel(QStringLiteral("No session active"));
        QFont f = none->font();
        f.setPixelSize(12);
        f.setItalic(true);
        none->setFont(f);
        none->setStyleSheet(QStringLiteral("color:%1; padding:6px 0;")
                                .arg(theme::hex(theme::Dim)));
        m_sessionBox->addWidget(none);
        return;
    }
    m_sessionBox->addWidget(
        buildField(QStringLiteral("Subject"), m_session.subject, true, false));
    m_sessionBox->addWidget(
        buildField(QStringLiteral("Operator"), m_session.op, false, false));
    m_sessionBox->addWidget(
        buildField(QStringLiteral("File"), m_session.filename, true, false));
    if (!m_session.notes.isEmpty())
        m_sessionBox->addWidget(
            buildField(QStringLiteral("Notes"), m_session.notes, false, false));
    m_sessionBox->addWidget(buildField(
        QStringLiteral("Started"),
        m_recording ? m_session.startedAtClock : QStringLiteral("preview only"),
        m_recording, !m_recording));
}

void Sidebar::rebuildMarkers()
{
    QLayoutItem *it;
    while ((it = m_markerList->takeAt(0))) {
        if (it->widget())
            it->widget()->deleteLater();
        delete it;
    }
    m_markerCount->setText(QString::number(m_markers.size()));

    if (m_markers.isEmpty()) {
        auto *hint = new QLabel(
            QStringLiteral("Press M or the marker button to flag a moment."));
        hint->setWordWrap(true);
        QFont f = hint->font();
        f.setPixelSize(11);
        hint->setFont(f);
        hint->setStyleSheet(QStringLiteral("color:%1; padding:4px 0;")
                                .arg(theme::hex(theme::Dim)));
        m_markerList->addWidget(hint);
        return;
    }
    for (int i = m_markers.size() - 1; i >= 0; --i) {
        const Marker &mk = m_markers[i];
        auto *roww = new QWidget;
        roww->setStyleSheet(QStringLiteral(
            "background:%1; border-radius:6px;")
            .arg(theme::hex(theme::TraceArea)));
        auto *row = new QHBoxLayout(roww);
        row->setContentsMargins(8, 6, 8, 6);
        row->setSpacing(8);

        auto *ts = new QLabel(fmt::elapsed(mk.elapsedMs));
        {
            QFont f(theme::monoFontFamily());
            f.setPixelSize(11);
            ts->setFont(f);
            ts->setStyleSheet(QStringLiteral("color:%1; background:transparent;")
                                  .arg(theme::hex(theme::Accent)));
        }
        auto *lbl = new QLabel(mk.label);
        {
            QFont f = lbl->font();
            f.setPixelSize(11);
            lbl->setFont(f);
            lbl->setStyleSheet(QStringLiteral("background:transparent;"));
        }
        auto *del = new QPushButton(QStringLiteral("×"));
        del->setCursor(Qt::PointingHandCursor);
        del->setFixedSize(18, 18);
        del->setStyleSheet(QStringLiteral(
            "QPushButton{background:transparent; border:none; color:%1;"
            "font-size:13px;} QPushButton:hover{color:%2;}")
            .arg(theme::hex(theme::Dim), theme::hex(theme::Text)));
        const int id = mk.id;
        connect(del, &QPushButton::clicked, this,
                [this, id] { emit removeMarkerRequested(id); });

        row->addWidget(ts);
        row->addWidget(lbl, 1);
        row->addWidget(del);
        m_markerList->addWidget(roww);
    }
}

// ================================ Topbar ==================================

Topbar::Topbar(QWidget *parent) : QWidget(parent)
{
    setFixedHeight(theme::TopbarHeight);
    setStyleSheet(QStringLiteral("border-bottom:1px solid %1;")
                      .arg(theme::hex(theme::Border)));

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(28, 0, 28, 0);
    row->setSpacing(18);

    auto *left = new QVBoxLayout;
    left->setSpacing(2);
    m_kicker = new QLabel;
    {
        QFont f = m_kicker->font();
        f.setPixelSize(11);
        m_kicker->setFont(f);
        m_kicker->setStyleSheet(QStringLiteral("color:%1;")
                                    .arg(theme::hex(theme::Muted)));
    }
    m_title = new QLabel;
    {
        QFont f = m_title->font();
        f.setPixelSize(16);
        f.setWeight(QFont::DemiBold);
        m_title->setFont(f);
    }
    left->addStretch(1);
    left->addWidget(m_kicker);
    left->addWidget(m_title);
    left->addStretch(1);
    row->addLayout(left);

    // recording pill
    m_recPill = new QWidget;
    m_recPill->setStyleSheet(QStringLiteral(
        "background:rgba(255,77,90,0.12);"
        "border:1px solid rgba(255,77,90,0.40);"
        "border-radius:12px;"));
    auto *pill = new QHBoxLayout(m_recPill);
    pill->setContentsMargins(12, 6, 12, 6);
    pill->setSpacing(8);
    auto *pdot = new QLabel;
    pdot->setFixedSize(8, 8);
    pdot->setStyleSheet(QStringLiteral(
        "background:%1; border-radius:4px;").arg(theme::hex(theme::Danger)));
    auto *ptext = new QLabel(QStringLiteral("RECORDING"));
    {
        QFont f = ptext->font();
        f.setPixelSize(11);
        f.setWeight(QFont::DemiBold);
        f.setLetterSpacing(QFont::AbsoluteSpacing, 1.0);
        ptext->setFont(f);
        ptext->setStyleSheet(QStringLiteral("color:%1; border:none;")
                                 .arg(theme::hex(theme::Danger)));
    }
    pill->addWidget(pdot, 0, Qt::AlignVCenter);
    pill->addWidget(ptext, 0, Qt::AlignVCenter);
    row->addWidget(m_recPill, 0, Qt::AlignVCenter);

    auto *blink = new QTimer(this);
    blink->setInterval(600);
    connect(blink, &QTimer::timeout, this, [pdot, this] {
        static bool on = true;
        on = !on;
        pdot->setStyleSheet(QStringLiteral("background:%1; border-radius:4px;")
            .arg(on ? theme::hex(theme::Danger)
                    : QStringLiteral("rgba(255,77,90,0.35)")));
    });
    blink->start();

    row->addStretch(1);

    auto *filters = ui::button(QStringLiteral("Filters"),
                               ui::ButtonVariant::Ghost);
    connect(filters, &QPushButton::clicked, this, &Topbar::filtersRequested);
    row->addWidget(filters);

    m_newSession = ui::button(QStringLiteral("＋ New session"),
                              ui::ButtonVariant::Subtle);
    connect(m_newSession, &QPushButton::clicked, this,
            &Topbar::newSessionRequested);
    row->addWidget(m_newSession);

    m_primary = ui::button(QStringLiteral("●  Start recording"),
                           ui::ButtonVariant::Primary);
    connect(m_primary, &QPushButton::clicked, this, &Topbar::startRequested);
    row->addWidget(m_primary);

    m_danger = ui::button(QStringLiteral("■  Stop recording"),
                          ui::ButtonVariant::Danger);
    connect(m_danger, &QPushButton::clicked, this, &Topbar::stopRequested);
    row->addWidget(m_danger);

    refresh();
}

void Topbar::setRecording(bool on)
{
    m_recording = on;
    refresh();
}

void Topbar::setSession(const Session &s, bool hasSession)
{
    m_session = s;
    m_hasSession = hasSession;
    refresh();
}

void Topbar::refresh()
{
    m_kicker->setText(m_recording ? QStringLiteral("Recording session")
                                  : QStringLiteral("Live preview"));
    m_title->setText(m_hasSession
                         ? m_session.subject + QStringLiteral(" · ")
                               + m_session.filename
                         : QStringLiteral("Ready to record"));
    m_recPill->setVisible(m_recording);
    m_newSession->setVisible(!m_recording);
    m_primary->setVisible(!m_recording);
    m_danger->setVisible(m_recording);
}

// =============================== MetricBar ================================

namespace {

QWidget *metricCell(const QString &label, QLabel **valueOut,
                     bool mono, const QColor &valueColor)
{
    auto *w = new QWidget;
    auto *v = new QVBoxLayout(w);
    v->setContentsMargins(24, 13, 24, 13);
    v->setSpacing(4);
    auto *l = new QLabel(label.toUpper());
    {
        QFont f = l->font();
        f.setPixelSize(11);
        f.setLetterSpacing(QFont::AbsoluteSpacing, 0.6);
        l->setFont(f);
        l->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    }
    auto *val = new QLabel;
    {
        QFont f = mono ? QFont(theme::monoFontFamily()) : val->font();
        f.setPixelSize(16);
        f.setWeight(QFont::DemiBold);
        val->setFont(f);
        val->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(valueColor)));
    }
    v->addWidget(l);
    v->addWidget(val);
    *valueOut = val;
    return w;
}

} // namespace

MetricBar::MetricBar(QWidget *parent) : QWidget(parent)
{
    setStyleSheet(QStringLiteral("border-bottom:1px solid %1;")
                      .arg(theme::hex(theme::Border)));
    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(0);

    QLabel *sig = nullptr;
    auto *c1 = metricCell(QStringLiteral("Elapsed"), &m_elapsedV, false, theme::Text);
    auto *c2 = metricCell(QStringLiteral("Samples"), &m_samplesV, true, theme::Text);
    auto *c3 = metricCell(QStringLiteral("Disk used"), &m_diskV, false, theme::Text);
    auto *c4 = metricCell(QStringLiteral("Signal quality"), &sig, false, theme::Accent);
    auto *c5 = metricCell(QStringLiteral("Clock"), &m_clockV, true, theme::Text);
    sig->setText(QStringLiteral("Good"));

    QWidget *cells[] = {c1, c2, c3, c4, c5};
    for (int i = 0; i < 5; ++i) {
        row->addWidget(cells[i], 1);
        if (i < 4)
            row->addWidget(ui::vLine());
    }

    setElapsed(0);
    m_clockV->setText(QStringLiteral("00:00:00"));
}

void MetricBar::setRecording(bool on)
{
    m_recording = on;
    m_elapsedV->setStyleSheet(QStringLiteral("color:%1;")
        .arg(theme::hex(on ? theme::Accent : theme::Text)));
    setElapsed(m_elapsed);
}

void MetricBar::setElapsed(qint64 ms)
{
    m_elapsed = ms;
    m_elapsedV->setText(fmt::elapsed(ms));
    m_samplesV->setText(m_recording ? fmt::samples(ms) : QStringLiteral("0"));
    m_diskV->setText(m_recording ? fmt::diskMB(ms) : QStringLiteral("0 MB"));
}

void MetricBar::setClock(const QString &c)
{
    m_clockV->setText(c);
}

// =============================== MonitorView ==============================

MonitorView::MonitorView(QWidget *parent) : QWidget(parent)
{
    auto *root = new QHBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    m_sidebar = new Sidebar;
    root->addWidget(m_sidebar);

    auto *right = new QWidget;
    auto *rv = new QVBoxLayout(right);
    rv->setContentsMargins(0, 0, 0, 0);
    rv->setSpacing(0);

    m_topbar = new Topbar;
    m_metrics = new MetricBar;
    rv->addWidget(m_topbar);
    rv->addWidget(m_metrics);

    // Content area: EEG fills the whole padded inner rect; the VideoDock
    // (which embeds a VideoCanvas) floats over the EEG corner -- it can
    // be dragged to any corner and resized from its inner edge. The dock
    // is parented to m_eeg so it inherits its rect for snap geometry and
    // gets repositioned automatically on EEG resize.
    auto *content = new QWidget;
    auto *cl = new QHBoxLayout(content);
    cl->setContentsMargins(theme::ContentPad, theme::ContentPad,
                           theme::ContentPad, theme::ContentPad);
    cl->setSpacing(0);
    m_eeg = new EegCanvas;
    cl->addWidget(m_eeg, 1);
    rv->addWidget(content, 1);

    m_videoDock = new VideoDock(m_eeg);
    m_video     = m_videoDock->findChild<VideoCanvas *>();
    m_eeg->setVideoDock(m_videoDock);

    root->addWidget(right, 1);

    // keyboard hints (floating, bottom-right)
    m_hints = new QWidget(this);
    m_hints->setAttribute(Qt::WA_TransparentForMouseEvents);
    auto *hl = new QHBoxLayout(m_hints);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(10);

    connect(m_topbar, &Topbar::startRequested, this, &MonitorView::startRequested);
    connect(m_topbar, &Topbar::stopRequested, this, &MonitorView::stopRequested);
    connect(m_topbar, &Topbar::newSessionRequested, this, &MonitorView::newSessionRequested);
    connect(m_topbar, &Topbar::filtersRequested, this, &MonitorView::filtersRequested);
    connect(m_sidebar, &Sidebar::addMarkerRequested, this, &MonitorView::addMarkerRequested);
    connect(m_sidebar, &Sidebar::removeMarkerRequested, this, &MonitorView::removeMarkerRequested);

    setScreen(Screen::Preview);
}

void MonitorView::setScreen(Screen s)
{
    m_screen = s;
    const bool rec = (s == Screen::Recording);
    m_topbar->setRecording(rec);
    m_metrics->setRecording(rec);
    m_sidebar->setRecording(rec);
    m_eeg->setRecording(rec);
    m_videoDock->setRecording(rec);
    m_videoDock->setTimecode(rec ? fmt::elapsed(0) : QStringLiteral("Live"));
    layoutHints();
}

void MonitorView::setSession(const Session &s, bool hasSession)
{
    m_topbar->setSession(s, hasSession);
    m_sidebar->setSession(s, hasSession);
}

void MonitorView::setDevices(const Devices &d) { m_sidebar->setDevices(d); }
void MonitorView::setFilters(const Filters &f) { m_sidebar->setFilters(f); }
void MonitorView::setMarkers(const QVector<Marker> &m) { m_sidebar->setMarkers(m); }

void MonitorView::setElapsed(qint64 ms)
{
    m_metrics->setElapsed(ms);
    if (m_screen == Screen::Recording)
        m_videoDock->setTimecode(fmt::elapsed(ms));
}

void MonitorView::setClock(const QString &c) { m_metrics->setClock(c); }

void MonitorView::layoutHints()
{
    QLayout *l = m_hints->layout();
    QLayoutItem *it;
    while ((it = l->takeAt(0))) {
        if (it->widget())
            it->widget()->deleteLater();
        delete it;
    }

    QVector<QPair<QString, QString>> hints;
    if (m_screen == Screen::Preview)
        hints = {{QStringLiteral("Space"), QStringLiteral("start")},
                 {QStringLiteral("F"), QStringLiteral("filters")}};
    else
        hints = {{QStringLiteral("Space"), QStringLiteral("stop")},
                 {QStringLiteral("M"), QStringLiteral("marker")},
                 {QStringLiteral("F"), QStringLiteral("filters")}};

    for (const auto &h : hints) {
        auto *item = new QWidget;
        auto *r = new QHBoxLayout(item);
        r->setContentsMargins(0, 0, 0, 0);
        r->setSpacing(6);
        r->addWidget(ui::kbd(h.first));
        auto *lab = new QLabel(h.second);
        QFont f = lab->font();
        f.setPixelSize(11);
        lab->setFont(f);
        lab->setStyleSheet(QStringLiteral("color:%1; background:transparent;")
                               .arg(theme::hex(theme::Dim)));
        r->addWidget(lab);
        static_cast<QHBoxLayout *>(l)->addWidget(item);
    }
    m_hints->adjustSize();
    QResizeEvent re(size(), size());
    resizeEvent(&re);
}

void MonitorView::resizeEvent(QResizeEvent *e)
{
    QWidget::resizeEvent(e);
    m_hints->adjustSize();
    const QSize hs = m_hints->sizeHint();
    m_hints->setGeometry(width() - hs.width() - 22,
                         height() - hs.height() - 14,
                         hs.width(), hs.height());
    m_hints->raise();
}
