#include "theme.h"

#include <QFontDatabase>
#include <QStringList>

namespace theme {

namespace {

QString pickFamily(const QStringList &preferred, const QString &fallback)
{
    const QStringList installed = QFontDatabase::families();
    for (const QString &want : preferred) {
        for (const QString &have : installed) {
            if (have.compare(want, Qt::CaseInsensitive) == 0)
                return have;
        }
    }
    return fallback;
}

} // namespace

QString uiFontFamily()
{
    static const QString family =
        pickFamily({QStringLiteral("Inter"), QStringLiteral("Segoe UI")},
                   QStringLiteral("Segoe UI"));
    return family;
}

QString monoFontFamily()
{
    static const QString family =
        pickFamily({QStringLiteral("JetBrains Mono"),
                    QStringLiteral("Cascadia Mono"),
                    QStringLiteral("Consolas")},
                   QStringLiteral("Consolas"));
    return family;
}

QString styleSheet()
{
    const QString ui   = uiFontFamily();
    const QString mono = monoFontFamily();

    return QStringLiteral(R"(
* {
    font-family: "%UI%";
    color: %TEXT%;
    outline: none;
}

QWidget#root, QMainWindow {
    background: %BG%;
}

QToolTip {
    background: %PANELD%;
    color: %TEXT%;
    border: 1px solid %BORDER%;
    padding: 4px 8px;
}

/* ---- Panels ---------------------------------------------------------- */
QFrame[panel="true"] {
    background: %PANEL%;
    border: 1px solid %BORDER%;
    border-radius: %R%px;
}

/* ---- Buttons --------------------------------------------------------- */
QPushButton {
    font-weight: 600;
    font-size: 12px;
    padding: 8px 16px;
    border-radius: %R%px;
    background: transparent;
}
QPushButton[size="sm"] { padding: 6px 12px; font-size: 11px; }

QPushButton[variant="primary"] {
    background: %ACCENT%;
    color: %BG%;
    border: none;
}
QPushButton[variant="primary"]:hover  { background: #6fded3; }
QPushButton[variant="primary"]:pressed { background: #52bdb3; }

QPushButton[variant="ghost"] {
    background: transparent;
    color: %TEXT%;
    border: 1px solid %GHOST%;
}
QPushButton[variant="ghost"]:hover  { border-color: %ACCENT%; }
QPushButton[variant="ghost"]:pressed { background: %PANEL%; }

QPushButton[variant="subtle"] {
    background: %TRACE%;
    color: %TEXT%;
    border: 1px solid %BORDER%;
}
QPushButton[variant="subtle"]:hover { border-color: %GHOST%; }

QPushButton[variant="danger"] {
    background: %DANGER%;
    color: #ffffff;
    border: none;
}
QPushButton[variant="danger"]:hover  { background: #ff626d; }
QPushButton[variant="danger"]:pressed { background: #e0454f; }

QPushButton:disabled { color: %DIM%; }

/* ---- Inputs ---------------------------------------------------------- */
QLineEdit {
    background: %BG%;
    color: %TEXT%;
    border: 1px solid %BORDERIN%;
    border-radius: %R%px;
    padding: 9px 12px;
    font-size: 13px;
    selection-background-color: %ACCENTDIM%;
    selection-color: #ffffff;
}
QLineEdit:focus { border-color: %ACCENT%; }
QLineEdit[mono="true"] { font-family: "%MONO%"; }

/* ---- Scrollbars ------------------------------------------------------ */
QScrollBar:vertical   { background: %BG%; width: 10px; margin: 0; }
QScrollBar:horizontal { background: %BG%; height: 10px; margin: 0; }
QScrollBar::handle {
    background: %BORDERIN%;
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:hover { background: %GHOST%; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
)")
        .replace(QStringLiteral("%UI%"), ui)
        .replace(QStringLiteral("%MONO%"), mono)
        .replace(QStringLiteral("%BG%"), hex(Bg))
        .replace(QStringLiteral("%PANEL%"), hex(Panel))
        .replace(QStringLiteral("%PANELD%"), hex(PanelDark))
        .replace(QStringLiteral("%TRACE%"), hex(TraceArea))
        .replace(QStringLiteral("%BORDERIN%"), hex(BorderInput))
        .replace(QStringLiteral("%BORDER%"), hex(Border))
        .replace(QStringLiteral("%GHOST%"), hex(BorderGhost))
        .replace(QStringLiteral("%TEXT%"), hex(Text))
        .replace(QStringLiteral("%MUTED%"), hex(Muted))
        .replace(QStringLiteral("%DIM%"), hex(Dim))
        .replace(QStringLiteral("%ACCENTDIM%"), hex(AccentDim))
        .replace(QStringLiteral("%ACCENT%"), hex(Accent))
        .replace(QStringLiteral("%DANGER%"), hex(Danger))
        .replace(QStringLiteral("%R%"), QString::number(Radius));
}

} // namespace theme
