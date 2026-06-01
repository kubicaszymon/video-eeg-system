#include "uihelpers.h"
#include "theme.h"

#include <QFrame>
#include <QLabel>
#include <QPushButton>

namespace ui {

namespace {

const char *variantName(ButtonVariant v)
{
    switch (v) {
    case ButtonVariant::Primary: return "primary";
    case ButtonVariant::Ghost:   return "ghost";
    case ButtonVariant::Subtle:  return "subtle";
    case ButtonVariant::Danger:  return "danger";
    }
    return "ghost";
}

} // namespace

QPushButton *button(const QString &text, ButtonVariant variant,
                     ButtonSize size, QWidget *parent)
{
    auto *b = new QPushButton(text, parent);
    b->setProperty("variant", QString::fromLatin1(variantName(variant)));
    b->setProperty("size", size == ButtonSize::Sm
                               ? QStringLiteral("sm")
                               : QStringLiteral("md"));
    b->setCursor(Qt::PointingHandCursor);
    b->setFocusPolicy(Qt::TabFocus);
    return b;
}

QLabel *kbd(const QString &key, QWidget *parent)
{
    auto *l = new QLabel(key, parent);
    l->setAlignment(Qt::AlignCenter);
    l->setStyleSheet(QStringLiteral(
        "background:%1; border:1px solid %2; border-radius:4px;"
        "padding:1px 6px; color:%3; font-family:'%4'; font-size:10px;")
        .arg(theme::hex(theme::TraceArea),
             theme::hex(theme::BorderInput),
             theme::hex(theme::Text),
             theme::monoFontFamily()));
    return l;
}

QFrame *hLine(QWidget *parent)
{
    auto *f = new QFrame(parent);
    f->setFixedHeight(1);
    f->setStyleSheet(QStringLiteral("background:%1;").arg(theme::hex(theme::Border)));
    return f;
}

QFrame *vLine(QWidget *parent)
{
    auto *f = new QFrame(parent);
    f->setFixedWidth(1);
    f->setStyleSheet(QStringLiteral("background:%1;").arg(theme::hex(theme::Border)));
    return f;
}

QLabel *sectionCaption(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text.toUpper(), parent);
    QFont f = l->font();
    f.setPixelSize(10);
    f.setWeight(QFont::DemiBold);
    f.setLetterSpacing(QFont::AbsoluteSpacing, 1.4);
    l->setFont(f);
    l->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Dim)));
    return l;
}

void makePanel(QFrame *frame)
{
    frame->setProperty("panel", true);
    frame->setFrameShape(QFrame::NoFrame);
}

} // namespace ui
