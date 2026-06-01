#include "welcomescreen.h"
#include "theme.h"
#include "uihelpers.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

namespace {

QLabel *dot()
{
    auto *d = new QLabel;
    d->setFixedSize(7, 7);
    d->setStyleSheet(QStringLiteral(
        "background:%1; border-radius:3px;").arg(theme::hex(theme::Accent)));
    return d;
}

QLabel *brandMark(int side, int fontPx)
{
    auto *m = new QLabel(QStringLiteral("ψ"));
    m->setFixedSize(side, side);
    m->setAlignment(Qt::AlignCenter);
    m->setStyleSheet(QStringLiteral(
        "background:%1; color:%2; border-radius:6px;"
        "font-weight:700; font-size:%3px;")
        .arg(theme::hex(theme::Accent), theme::hex(theme::Bg))
        .arg(fontPx));
    return m;
}

} // namespace

// ------------------------------- DeviceCard -------------------------------

DeviceCard::DeviceCard(const QString &caption, QWidget *parent)
    : QFrame(parent)
{
    ui::makePanel(this);

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(18, 14, 18, 14);
    row->setSpacing(14);

    row->addWidget(dot(), 0, Qt::AlignVCenter);

    auto *col = new QVBoxLayout;
    col->setContentsMargins(0, 0, 0, 0);
    col->setSpacing(2);

    auto *cap = new QLabel(caption.toUpper());
    {
        QFont f = cap->font();
        f.setPixelSize(11);
        f.setLetterSpacing(QFont::AbsoluteSpacing, 0.4);
        cap->setFont(f);
        cap->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    }

    m_value = new QLabel;
    {
        QFont f = m_value->font();
        f.setPixelSize(14);
        f.setWeight(QFont::DemiBold);
        m_value->setFont(f);
    }

    m_sub = new QLabel;
    {
        QFont f(theme::monoFontFamily());
        f.setPixelSize(11);
        m_sub->setFont(f);
        m_sub->setStyleSheet(QStringLiteral("color:%1;").arg(theme::hex(theme::Muted)));
    }

    col->addWidget(cap);
    col->addWidget(m_value);
    col->addWidget(m_sub);
    row->addLayout(col, 1);
}

void DeviceCard::setDevice(const Device &d)
{
    m_value->setText(d.label);
    m_sub->setText(d.sub);
    m_sub->setVisible(!d.sub.isEmpty());
}

// ------------------------------ WelcomeScreen -----------------------------

WelcomeScreen::WelcomeScreen(QWidget *parent)
    : QWidget(parent)
{
    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    // brand bar
    auto *bar = new QWidget;
    bar->setFixedHeight(theme::BrandbarHeight);
    bar->setStyleSheet(QStringLiteral(
        "border-bottom:1px solid %1;").arg(theme::hex(theme::Border)));
    auto *barRow = new QHBoxLayout(bar);
    barRow->setContentsMargins(28, 0, 28, 0);
    barRow->setSpacing(10);
    barRow->addWidget(brandMark(26, 13), 0, Qt::AlignVCenter);
    auto *brandText = new QLabel(QStringLiteral("NeuroSync VEEG"));
    {
        QFont f = brandText->font();
        f.setPixelSize(13);
        f.setWeight(QFont::DemiBold);
        brandText->setFont(f);
    }
    barRow->addWidget(brandText, 0, Qt::AlignVCenter);
    barRow->addStretch(1);
    outer->addWidget(bar);

    // centred content column
    auto *centerRow = new QHBoxLayout;
    centerRow->addStretch(1);

    auto *col = new QWidget;
    col->setFixedWidth(520);
    auto *colLay = new QVBoxLayout(col);
    colLay->setContentsMargins(0, 0, 0, 0);
    colLay->setSpacing(10);

    m_amp = new DeviceCard(QStringLiteral("Amplifier"));
    m_camera = new DeviceCard(QStringLiteral("Camera"));
    m_storage = new DeviceCard(QStringLiteral("Storage"));
    for (DeviceCard *c : {m_amp, m_camera, m_storage})
        colLay->addWidget(c);

    auto *start = ui::button(QStringLiteral("＋  Start new session"),
                             ui::ButtonVariant::Primary);
    {
        QFont f = start->font();
        f.setPixelSize(14);
        f.setWeight(QFont::DemiBold);
        start->setFont(f);
    }
    start->setMinimumHeight(44);
    connect(start, &QPushButton::clicked, this, &WelcomeScreen::startRequested);
    colLay->addSpacing(6);
    colLay->addWidget(start);

    auto *centerCol = new QVBoxLayout;
    centerCol->addStretch(1);
    centerCol->addWidget(col);
    centerCol->addStretch(1);
    centerRow->addLayout(centerCol);
    centerRow->addStretch(1);
    outer->addLayout(centerRow, 1);
}

void WelcomeScreen::setDevices(const Devices &d)
{
    m_amp->setDevice(d.amp);
    m_camera->setDevice(d.camera);
    m_storage->setDevice(d.storage);
}
