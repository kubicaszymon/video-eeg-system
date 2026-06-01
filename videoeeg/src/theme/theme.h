#pragma once

// Design tokens for the "Modern Research" (Variant C) direction.
// Values are the final committed choices from the design hand-off:
// cyan accent, Inter typography, comfortable density, 10 px corner radius.

#include <QColor>
#include <QString>

namespace theme {

// ---- Palette ---------------------------------------------------------------
inline const QColor Bg          = QColor(0x0c, 0x0e, 0x11);
inline const QColor Panel       = QColor(0x13, 0x16, 0x1b);
inline const QColor PanelDark   = QColor(0x10, 0x13, 0x1a);
inline const QColor TraceArea   = QColor(0x1a, 0x1e, 0x24);
inline const QColor Border      = QColor(0x24, 0x29, 0x31);
inline const QColor BorderInput = QColor(0x2c, 0x32, 0x3b);
inline const QColor BorderSub   = QColor(0x1f, 0x24, 0x2c);
inline const QColor BorderGhost = QColor(0x33, 0x3a, 0x44);
inline const QColor Text        = QColor(0xe7, 0xec, 0xf2);
inline const QColor Muted       = QColor(0x8c, 0x95, 0xa3);
inline const QColor Dim         = QColor(0x5d, 0x65, 0x73);
inline const QColor Accent      = QColor(0x5f, 0xd0, 0xc5);
inline const QColor AccentDim   = QColor(0x2a, 0x6e, 0x68);
inline const QColor AccentGlow  = QColor(0x5f, 0xd0, 0xc5, 31);   // ~0.12 alpha
inline const QColor Danger      = QColor(0xff, 0x4d, 0x5a);
inline const QColor Warn        = QColor(0xfb, 0xbf, 0x24);

// ---- Metrics ---------------------------------------------------------------
constexpr int Radius        = 10;
constexpr int SidebarWidth  = 260;
constexpr int TopbarHeight  = 68;
constexpr int BrandbarHeight = 56;
constexpr int VideoWidth    = 380;
constexpr int ContentPad    = 22;   // comfortable density
constexpr int ContentGap    = 22;

// ---- Typography ------------------------------------------------------------
// Inter / JetBrains Mono are the design fonts; fall back to clean Windows
// system fonts when they are not installed so the app still looks right.
QString uiFontFamily();
QString monoFontFamily();

// ---- Global stylesheet -----------------------------------------------------
QString styleSheet();

inline QString hex(const QColor &c)
{
    return c.alpha() == 255
        ? c.name(QColor::HexRgb)
        : QStringLiteral("rgba(%1,%2,%3,%4)")
              .arg(c.red()).arg(c.green()).arg(c.blue())
              .arg(c.alphaF(), 0, 'f', 3);
}

} // namespace theme
