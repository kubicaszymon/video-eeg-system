#include "overlays.h"
#include "format.h"
#include "theme.h"
#include "uihelpers.h"

#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QMouseEvent>
#include <QPainter>
#include <QPushButton>
#include <QShowEvent>
#include <QTimer>
#include <QVBoxLayout>

#include <functional>

// ---------------------------------------------------------------------------
namespace {

QLabel *fieldCaption(const QString &t)
{
    auto *l = new QLabel(t);
    QFont f = l->font();
    f.setPixelSize(11);
    l->setFont(f);
    l->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    return l;
}

QWidget *lineField(const QString &caption, QLineEdit **out,
                    bool mono, const QString &placeholder = {})
{
    auto *w = new QWidget;
    auto *v = new QVBoxLayout(w);
    v->setContentsMargins(0, 0, 0, 0);
    v->setSpacing(5);
    v->addWidget(fieldCaption(caption));
    auto *e = new QLineEdit;
    if (mono)
        e->setProperty("mono", true);
    if (!placeholder.isEmpty())
        e->setPlaceholderText(placeholder);
    v->addWidget(e);
    *out = e;
    return w;
}

QWidget *dialogStat(const QString &label, QLabel **out, bool mono)
{
    auto *w = new QWidget;
    auto *v = new QVBoxLayout(w);
    v->setContentsMargins(0, 0, 0, 0);
    v->setSpacing(3);
    auto *l = new QLabel(label.toUpper());
    {
        QFont f = l->font();
        f.setPixelSize(11);
        f.setLetterSpacing(QFont::AbsoluteSpacing, 0.4);
        l->setFont(f);
        l->setStyleSheet(QStringLiteral("color:%1; background:transparent;")
                             .arg(theme::hex(theme::Muted)));
    }
    auto *val = new QLabel;
    {
        QFont f = mono ? QFont(theme::monoFontFamily()) : val->font();
        f.setPixelSize(14);
        f.setWeight(QFont::DemiBold);
        val->setFont(f);
        val->setStyleSheet(QStringLiteral("background:transparent;"));
    }
    v->addWidget(l);
    v->addWidget(val);
    *out = val;
    return w;
}

} // namespace

// ============================== ModalOverlay ==============================

ModalOverlay::ModalOverlay(QWidget *parent) : QWidget(parent)
{
    setAttribute(Qt::WA_StyledBackground, false);
    hide();

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->addStretch(1);
    auto *mid = new QHBoxLayout;
    mid->addStretch(1);

    m_card = new QFrame;
    m_card->setObjectName(QStringLiteral("card"));
    m_card->setStyleSheet(QStringLiteral(
        "QFrame#card{background:%1; border:1px solid %2; border-radius:12px;}")
        .arg(theme::hex(theme::Panel), theme::hex(theme::Border)));
    m_card->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Maximum);
    m_card->setFixedWidth(480);

    auto *cardLay = new QVBoxLayout(m_card);
    cardLay->setContentsMargins(0, 0, 0, 0);
    cardLay->setSpacing(0);

    auto *titleHost = new QWidget;
    auto *th = new QVBoxLayout(titleHost);
    th->setContentsMargins(24, 20, 24, 0);
    m_title = new QLabel;
    {
        QFont f = m_title->font();
        f.setPixelSize(16);
        f.setWeight(QFont::DemiBold);
        m_title->setFont(f);
    }
    th->addWidget(m_title);
    cardLay->addWidget(titleHost);

    auto *bodyHost = new QWidget;
    m_body = new QVBoxLayout(bodyHost);
    m_body->setContentsMargins(24, 18, 24, 18);
    cardLay->addWidget(bodyHost);

    m_footer = new QWidget;
    // Use an ID selector so the footer's background does NOT cascade into
    // child QPushButtons (which would clobber their variant=primary
    // background and make the primary "Continue / Save" button invisible).
    m_footer->setObjectName(QStringLiteral("modalFooter"));
    m_footer->setStyleSheet(QStringLiteral(
        "QWidget#modalFooter { background:%1; border-top:1px solid %2; }")
        .arg(theme::hex(theme::PanelDark), theme::hex(theme::Border)));
    auto *fh = new QHBoxLayout(m_footer);
    fh->setContentsMargins(24, 14, 24, 14);
    fh->setSpacing(10);
    fh->addStretch(1);
    m_footer->setVisible(false);
    cardLay->addWidget(m_footer);

    mid->addWidget(m_card);
    mid->addStretch(1);
    outer->addLayout(mid);
    outer->addStretch(1);
}

void ModalOverlay::setCardWidth(int w) { m_card->setFixedWidth(w); }

void ModalOverlay::setTitleText(const QString &t) { m_title->setText(t); }

void ModalOverlay::setFooter(const QVector<QPushButton *> &buttons)
{
    auto *fh = static_cast<QHBoxLayout *>(m_footer->layout());
    for (QPushButton *b : buttons)
        fh->addWidget(b);
    m_footer->setVisible(!buttons.isEmpty());
}

void ModalOverlay::reposition()
{
    if (parentWidget())
        setGeometry(parentWidget()->rect());
}

void ModalOverlay::showOverlay()
{
    reposition();
    show();
    raise();
    setFocus();
}

void ModalOverlay::hideOverlay() { hide(); }

void ModalOverlay::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.fillRect(rect(), QColor(8, 10, 13, 166)); // ~0.65 alpha
}

void ModalOverlay::mousePressEvent(QMouseEvent *e)
{
    const QPoint inCard = m_card->mapFrom(this, e->pos());
    if (!m_card->rect().contains(inCard)) {
        emit cancelled();
        hideOverlay();
    }
}

void ModalOverlay::keyPressEvent(QKeyEvent *e)
{
    if (e->key() == Qt::Key_Escape) {
        emit cancelled();
        hideOverlay();
    } else {
        QWidget::keyPressEvent(e);
    }
}

void ModalOverlay::showEvent(QShowEvent *)
{
    reposition();
}

// ============================ NewSessionDialog ============================

NewSessionDialog::NewSessionDialog(QWidget *parent) : ModalOverlay(parent)
{
    setTitleText(QStringLiteral("New session"));

    auto *grid = new QWidget;
    auto *g = new QGridLayout(grid);
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(14);
    g->setVerticalSpacing(14);
    g->addWidget(lineField(QStringLiteral("Subject ID"), &m_subject, true), 0, 0);
    g->addWidget(lineField(QStringLiteral("Operator"), &m_operator, false), 0, 1);
    g->addWidget(lineField(QStringLiteral("Filename"), &m_filename, true), 1, 0, 1, 2);
    g->addWidget(lineField(QStringLiteral("Notes (optional)"), &m_notes, false,
                           QStringLiteral("e.g. day 2 of monitoring")),
                 2, 0, 1, 2);
    bodyLayout()->addWidget(grid);

    auto *cancel = ui::button(QStringLiteral("Cancel"), ui::ButtonVariant::Ghost);
    auto *go = ui::button(QStringLiteral("Continue to preview"),
                          ui::ButtonVariant::Primary);
    connect(cancel, &QPushButton::clicked, this, [this] {
        emit cancelled();
        hideOverlay();
    });
    connect(go, &QPushButton::clicked, this, [this] {
        Session s;
        s.subject = m_subject->text().trimmed();
        s.op = m_operator->text().trimmed();
        s.filename = m_filename->text().trimmed();
        s.notes = m_notes->text().trimmed();
        if (s.subject.isEmpty() || s.filename.isEmpty())
            return; // require the essentials before proceeding
        hideOverlay();
        emit confirmed(s);
    });
    setFooter({cancel, go});
}

void NewSessionDialog::openWith(const Session &d)
{
    m_subject->setText(d.subject);
    m_operator->setText(d.op);
    m_filename->setText(d.filename);
    m_notes->setText(d.notes);
    showOverlay();
    m_subject->setFocus();
    m_subject->selectAll();
}

// ============================ StopConfirmDialog ===========================

StopConfirmDialog::StopConfirmDialog(QWidget *parent) : ModalOverlay(parent)
{
    setTitleText(QStringLiteral("Stop recording?"));

    auto *box = new QFrame;
    box->setStyleSheet(QStringLiteral(
        "background:%1; border:1px solid %2; border-radius:%3px;")
        .arg(theme::hex(theme::PanelDark), theme::hex(theme::Border))
        .arg(theme::Radius));
    auto *g = new QGridLayout(box);
    g->setContentsMargins(14, 14, 14, 14);
    g->setHorizontalSpacing(10);
    g->setVerticalSpacing(10);
    g->addWidget(dialogStat(QStringLiteral("Duration"), &m_duration, true), 0, 0);
    g->addWidget(dialogStat(QStringLiteral("Markers"), &m_markers, false), 0, 1);
    g->addWidget(dialogStat(QStringLiteral("Subject"), &m_subject, true), 1, 0);
    g->addWidget(dialogStat(QStringLiteral("Operator"), &m_operator, false), 1, 1);
    g->addWidget(dialogStat(QStringLiteral("File"), &m_file, true), 2, 0, 1, 2);
    bodyLayout()->addWidget(box);

    auto *keep = ui::button(QStringLiteral("Keep recording"),
                            ui::ButtonVariant::Ghost);
    auto *discard = ui::button(QStringLiteral("Discard"),
                               ui::ButtonVariant::Subtle);
    auto *save = ui::button(QStringLiteral("Save recording"),
                            ui::ButtonVariant::Primary);
    connect(keep, &QPushButton::clicked, this, [this] {
        emit cancelled();
        hideOverlay();
    });
    connect(discard, &QPushButton::clicked, this, [this] {
        hideOverlay();
        emit discardRequested();
    });
    connect(save, &QPushButton::clicked, this, [this] {
        hideOverlay();
        emit saveRequested();
    });
    setFooter({keep, discard, save});
}

void StopConfirmDialog::openWith(qint64 elapsedMs, int markerCount,
                                 const Session &s)
{
    m_duration->setText(fmt::elapsed(elapsedMs));
    m_markers->setText(QString::number(markerCount));
    m_subject->setText(s.subject.isEmpty() ? QStringLiteral("—") : s.subject);
    m_operator->setText(s.op.isEmpty() ? QStringLiteral("—") : s.op);
    m_file->setText(s.filename.isEmpty() ? QStringLiteral("—") : s.filename);
    showOverlay();
}

// ============================= FiltersPopover =============================

namespace {

QWidget *segmented(const QString &caption, const QStringList &options,
                   const QString &selected,
                   const std::function<void(const QString &)> &onPick)
{
    auto *w = new QWidget;
    auto *v = new QVBoxLayout(w);
    v->setContentsMargins(0, 0, 0, 0);
    v->setSpacing(6);
    auto *cap = new QLabel(caption);
    {
        QFont f = cap->font();
        f.setPixelSize(11);
        cap->setFont(f);
        cap->setStyleSheet(QStringLiteral("color:%1; background:transparent;")
                               .arg(theme::hex(theme::Muted)));
    }
    v->addWidget(cap);

    auto *seg = new QFrame;
    seg->setStyleSheet(QStringLiteral(
        "background:%1; border:1px solid %2; border-radius:6px;")
        .arg(theme::hex(theme::Bg), theme::hex(theme::Border)));
    auto *h = new QHBoxLayout(seg);
    h->setContentsMargins(2, 2, 2, 2);
    h->setSpacing(0);
    for (const QString &opt : options) {
        const bool on = (opt == selected);
        auto *b = new QPushButton(opt);
        b->setCursor(Qt::PointingHandCursor);
        b->setMinimumHeight(26);
        b->setStyleSheet(QStringLiteral(
            "QPushButton{background:%1; color:%2; border:none;"
            "border-radius:5px; font-family:'%3'; font-size:11px;"
            "font-weight:%4;}")
            .arg(on ? theme::hex(theme::Accent)
                    : QStringLiteral("transparent"),
                 on ? theme::hex(theme::Bg) : theme::hex(theme::Text),
                 theme::monoFontFamily())
            .arg(on ? 700 : 500));
        QObject::connect(b, &QPushButton::clicked, b,
                         [opt, onPick] { onPick(opt); });
        h->addWidget(b, 1);
    }
    v->addWidget(seg);
    return w;
}

} // namespace

FiltersPopover::FiltersPopover(QWidget *parent) : QWidget(parent)
{
    hide();

    m_panel = new QFrame(this);
    m_panel->setFixedWidth(280);
    m_panel->setStyleSheet(QStringLiteral(
        "QFrame{background:%1; border:1px solid %2; border-radius:%3px;}")
        .arg(theme::hex(theme::Panel), theme::hex(theme::Border))
        .arg(theme::Radius));
    auto *v = new QVBoxLayout(m_panel);
    v->setContentsMargins(16, 16, 16, 16);
    v->setSpacing(0);

    auto *title = new QLabel(QStringLiteral("Signal filters"));
    {
        QFont f = title->font();
        f.setPixelSize(13);
        f.setWeight(QFont::DemiBold);
        title->setFont(f);
        title->setStyleSheet(QStringLiteral("background:transparent;"));
    }
    auto *sub = new QLabel(
        QStringLiteral("Applied to display and to the saved file."));
    {
        QFont f = sub->font();
        f.setPixelSize(11);
        sub->setFont(f);
        sub->setStyleSheet(QStringLiteral("color:%1; background:transparent;")
                               .arg(theme::hex(theme::Muted)));
    }
    v->addWidget(title);
    v->addSpacing(4);
    v->addWidget(sub);
    v->addSpacing(14);

    auto *rowsHost = new QWidget;
    rowsHost->setStyleSheet(QStringLiteral("background:transparent;"));
    m_rows = new QVBoxLayout(rowsHost);
    m_rows->setContentsMargins(0, 0, 0, 0);
    m_rows->setSpacing(12);
    v->addWidget(rowsHost);

    rebuild();
}

void FiltersPopover::setFilters(const Filters &f)
{
    m_filters = f;
    rebuild();
}

void FiltersPopover::rebuild()
{
    QLayoutItem *it;
    while ((it = m_rows->takeAt(0))) {
        if (it->widget())
            it->widget()->deleteLater();
        delete it;
    }

    const QString hpSel = QStringLiteral("%1 Hz").arg(m_filters.hp);
    m_rows->addWidget(segmented(
        QStringLiteral("High-pass"),
        {QStringLiteral("0.1 Hz"), QStringLiteral("0.5 Hz"),
         QStringLiteral("1 Hz"), QStringLiteral("5 Hz")},
        hpSel, [this](const QString &v) {
            m_filters.hp = v.split(' ').first().toDouble();
            emit filtersChanged(m_filters);
            rebuild();
        }));

    const QString lpSel = m_filters.lp == 0.0
                              ? QStringLiteral("off")
                              : QStringLiteral("%1 Hz").arg(m_filters.lp);
    m_rows->addWidget(segmented(
        QStringLiteral("Low-pass"),
        {QStringLiteral("30 Hz"), QStringLiteral("70 Hz"),
         QStringLiteral("100 Hz"), QStringLiteral("off")},
        lpSel, [this](const QString &v) {
            m_filters.lp = (v == QLatin1String("off"))
                               ? 0.0
                               : v.split(' ').first().toDouble();
            emit filtersChanged(m_filters);
            rebuild();
        }));

    const QString nSel = m_filters.notch == 0.0
                             ? QStringLiteral("off")
                             : QStringLiteral("%1 Hz").arg(m_filters.notch);
    m_rows->addWidget(segmented(
        QStringLiteral("Notch"),
        {QStringLiteral("off"), QStringLiteral("50 Hz"),
         QStringLiteral("60 Hz")},
        nSel, [this](const QString &v) {
            m_filters.notch = (v == QLatin1String("off"))
                                  ? 0.0
                                  : v.split(' ').first().toDouble();
            emit filtersChanged(m_filters);
            rebuild();
        }));
}

void FiltersPopover::toggle()
{
    if (isVisible()) {
        hide();
        return;
    }
    reposition();
    show();
    raise();
}

bool FiltersPopover::isOpen() const { return isVisible(); }

void FiltersPopover::reposition()
{
    if (!parentWidget())
        return;
    setGeometry(parentWidget()->rect());
    m_panel->adjustSize();
    m_panel->move(width() - m_panel->width() - 24, 60);
}

void FiltersPopover::mousePressEvent(QMouseEvent *e)
{
    if (!m_panel->geometry().contains(e->pos()))
        hide();
}

// =============================== SaveToast ================================

SaveToast::SaveToast(QWidget *parent) : QWidget(parent)
{
    setAttribute(Qt::WA_TransparentForMouseEvents);
    hide();

    auto *box = new QFrame(this);
    box->setStyleSheet(QStringLiteral(
        "QFrame{background:%1; border:1px solid %2; border-radius:%3px;}")
        .arg(theme::hex(theme::Panel), theme::hex(theme::AccentDim))
        .arg(theme::Radius));
    auto *h = new QHBoxLayout(box);
    h->setContentsMargins(18, 11, 18, 11);
    h->setSpacing(10);

    auto *check = new QLabel(QStringLiteral("✓"));
    check->setFixedSize(18, 18);
    check->setAlignment(Qt::AlignCenter);
    check->setStyleSheet(QStringLiteral(
        "background:%1; color:%2; border-radius:9px;"
        "font-weight:700; font-size:12px;")
        .arg(theme::hex(theme::Accent), theme::hex(theme::Bg)));
    m_text = new QLabel;
    {
        QFont f = m_text->font();
        f.setPixelSize(13);
        m_text->setFont(f);
        m_text->setStyleSheet(QStringLiteral("background:transparent;"));
    }
    h->addWidget(check);
    h->addWidget(m_text);

    auto *lay = new QVBoxLayout(this);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->addWidget(box);

    m_timer = new QTimer(this);
    m_timer->setSingleShot(true);
    m_timer->setInterval(3200);
    connect(m_timer, &QTimer::timeout, this, [this] { hide(); });
}

void SaveToast::show(const QString &message)
{
    m_text->setText(message);
    adjustSize();
    reposition();
    QWidget::show();
    raise();
    m_timer->start();
}

void SaveToast::reposition()
{
    if (!parentWidget())
        return;
    adjustSize();
    const QSize s = sizeHint();
    move((parentWidget()->width() - s.width()) / 2,
         parentWidget()->height() - s.height() - 24);
}
