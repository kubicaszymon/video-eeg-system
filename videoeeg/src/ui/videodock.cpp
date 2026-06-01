#include "videodock.h"

#include "canvases.h"
#include "theme.h"

#include <QFontMetrics>
#include <QHoverEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QSettings>

#include <algorithm>

namespace {
// Layout constants chosen to match the Claude Design mockup.
constexpr int kInset       = 14;     // distance from parent edge
constexpr int kHeaderH     = 28;
constexpr int kCorner      = 8;      // border radius
constexpr int kGripSize    = 14;
constexpr int kMinW        = 220;
constexpr int kMinH        = 160;
constexpr int kMaxW        = 1200;
constexpr int kMaxH        = 900;
constexpr int kPillW       = 140;
constexpr int kPillH       = 30;
constexpr int kMinBtn      = 22;     // square hit area for the minimize "_"
constexpr const char *kSettingsKey = "videoDock";
}

VideoDock::VideoDock(QWidget *parent) : QWidget(parent)
{
    setAttribute(Qt::WA_StyledBackground, false);
    setAutoFillBackground(false);
    setAttribute(Qt::WA_Hover, true);
    setMouseTracking(true);
    setCursor(Qt::ArrowCursor);

    m_canvas = new VideoCanvas(this);
    // VideoCanvas's mock placeholder pulls focus; we never want it grabbing
    // input -- all mouse handling on the dock is owned by VideoDock.
    m_canvas->setAttribute(Qt::WA_TransparentForMouseEvents, true);

    readState();
    layoutInner();
}

VideoDock::~VideoDock()
{
    writeState();
}

// --------------------------------------------------------------------------
// Public API (proxied to the inner VideoCanvas + own title bar state)
// --------------------------------------------------------------------------

void VideoDock::setRecording(bool on)
{
    if (m_recording == on) return;
    m_recording = on;
    m_canvas->setRecording(on);
    update();
}

void VideoDock::setTimecode(const QString &tc)
{
    if (m_timecode == tc) return;
    m_timecode = tc;
    update();
}

void VideoDock::setReceiver(LslVideoReceiver *recv)
{
    m_canvas->setReceiver(recv);
}

// --------------------------------------------------------------------------
// Reposition: read current state, set widget geometry inside parent rect.
// --------------------------------------------------------------------------

QPoint VideoDock::anchoredTopLeft(QSize sz) const
{
    if (!parentWidget()) return QPoint(0, 0);
    const QRect pr = parentWidget()->rect();
    switch (m_corner) {
    case TopLeft:     return QPoint(kInset, kInset);
    case TopRight:    return QPoint(pr.width()  - sz.width()  - kInset, kInset);
    case BottomLeft:  return QPoint(kInset, pr.height() - sz.height() - kInset);
    case BottomRight:
    default:          return QPoint(pr.width()  - sz.width()  - kInset,
                                    pr.height() - sz.height() - kInset);
    }
}

void VideoDock::reposition()
{
    if (!parentWidget()) return;

    QSize sz = m_minimized ? QSize(kPillW, kPillH) : m_size;
    // Clamp to parent if necessary (small parents).
    const QRect pr = parentWidget()->rect();
    sz.setWidth(std::min(sz.width(),  pr.width()  - 2 * kInset));
    sz.setHeight(std::min(sz.height(), pr.height() - 2 * kInset));
    sz.setWidth(std::max(sz.width(),  m_minimized ? kPillW : kMinW));
    sz.setHeight(std::max(sz.height(), m_minimized ? kPillH : kMinH));

    const QPoint tl = anchoredTopLeft(sz);
    setGeometry(QRect(tl, sz));
    layoutInner();
    raise();
}

void VideoDock::layoutInner()
{
    if (m_minimized) {
        m_canvas->hide();
        return;
    }
    m_canvas->show();
    m_canvas->setGeometry(bodyRect());
}

// --------------------------------------------------------------------------
// Geometry helpers (widget-local)
// --------------------------------------------------------------------------

QRect VideoDock::titleBarRect() const
{
    return QRect(0, 0, width(), kHeaderH);
}

QRect VideoDock::bodyRect() const
{
    return QRect(0, kHeaderH, width(), height() - kHeaderH);
}

QRect VideoDock::resizeGripRect() const
{
    // Inner corner -- opposite to the dock-anchored corner. So for a BR
    // dock the user grabs the grip in the TL inner edge of the body and
    // drags NW to grow, SE to shrink.  Reachable, intuitive.
    const QRect body = bodyRect();
    switch (m_corner) {
    case TopLeft:
        return QRect(body.right() - kGripSize + 1,
                     body.bottom() - kGripSize + 1, kGripSize, kGripSize);
    case TopRight:
        return QRect(body.left(),
                     body.bottom() - kGripSize + 1, kGripSize, kGripSize);
    case BottomLeft:
        return QRect(body.right() - kGripSize + 1,
                     body.top(), kGripSize, kGripSize);
    case BottomRight:
    default:
        return QRect(body.left(), body.top(), kGripSize, kGripSize);
    }
}

QRect VideoDock::minimizeBtnRect() const
{
    return QRect(width() - kMinBtn - 4,
                 (kHeaderH - kMinBtn) / 2, kMinBtn, kMinBtn);
}

QRect VideoDock::pillRect() const
{
    return QRect(0, 0, width(), height());
}

// --------------------------------------------------------------------------
// Painting
// --------------------------------------------------------------------------

void VideoDock::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    if (m_minimized) {
        // ---- pill ----------------------------------------------------
        QPainterPath path;
        path.addRoundedRect(QRectF(0.5, 0.5, width() - 1.0, height() - 1.0),
                            height() / 2.0, height() / 2.0);
        // semi-transparent dark fill + accent dot
        QColor bg = theme::Panel; bg.setAlpha(235);
        p.fillPath(path, bg);
        p.setPen(QPen(theme::Border, 1));
        p.drawPath(path);

        const int cy = height() / 2;
        const int dotR = 4;
        QColor dot = m_recording ? theme::Danger : theme::Accent;
        p.setBrush(dot);
        p.setPen(Qt::NoPen);
        p.drawEllipse(QPoint(14, cy), dotR, dotR);

        QFont f(theme::uiFontFamily());
        f.setPixelSize(11);
        f.setWeight(QFont::DemiBold);
        p.setFont(f);
        p.setPen(theme::Text);
        p.drawText(QRect(24, 0, 60, height()),
                   Qt::AlignVCenter | Qt::AlignLeft,
                   QStringLiteral("Camera"));

        QFont mono(theme::monoFontFamily());
        mono.setPixelSize(10);
        p.setFont(mono);
        p.setPen(theme::Muted);
        p.drawText(QRect(80, 0, width() - 86, height()),
                   Qt::AlignVCenter | Qt::AlignLeft, m_timecode);
        return;
    }

    // ---- full dock ---------------------------------------------------
    // Card background + rounded border.
    QPainterPath card;
    card.addRoundedRect(QRectF(0.5, 0.5, width() - 1.0, height() - 1.0),
                        kCorner, kCorner);
    p.fillPath(card, theme::Panel);
    p.setPen(QPen(theme::Border, 1));
    p.drawPath(card);

    // Title bar background (slightly lighter).
    const QRect tb = titleBarRect();
    p.save();
    p.setClipPath(card);
    QLinearGradient g(0, 0, 0, tb.height());
    g.setColorAt(0.0, QColor(0x18, 0x1c, 0x22));
    g.setColorAt(1.0, theme::Panel);
    p.fillRect(tb, g);
    p.setPen(QPen(theme::Border, 1));
    p.drawLine(0, tb.bottom(), width(), tb.bottom());
    p.restore();

    // Drag affordance — 6 dots in a 2x3 grid (matches the design).
    QColor dot = theme::Muted; dot.setAlpha(160);
    p.setBrush(dot); p.setPen(Qt::NoPen);
    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 2; ++col) {
            const QPointF c(10 + col * 4, 9 + row * 4);
            p.drawEllipse(c, 1.2, 1.2);
        }
    }

    // "Camera" label + recording dot if active.
    QFont lab(theme::uiFontFamily());
    lab.setPixelSize(12);
    lab.setWeight(QFont::DemiBold);
    p.setFont(lab);
    p.setPen(theme::Text);
    p.drawText(QRect(26, 0, width() - 26, kHeaderH),
               Qt::AlignVCenter | Qt::AlignLeft,
               QStringLiteral("Camera"));
    const int labW = QFontMetrics(lab).horizontalAdvance(
        QStringLiteral("Camera"));

    // Timecode (mono, muted) right after the label.
    QFont mono(theme::monoFontFamily());
    mono.setPixelSize(10);
    p.setFont(mono);
    p.setPen(theme::Muted);
    p.drawText(QRect(26 + labW + 10, 0,
                     width() - 26 - labW - 10 - kMinBtn - 12, kHeaderH),
               Qt::AlignVCenter | Qt::AlignLeft, m_timecode);

    // Minimize button: a small underscore-style line.
    const QRect mb = minimizeBtnRect();
    if (m_hoverMinBtn) {
        QColor hb = theme::BorderInput; hb.setAlpha(180);
        QPainterPath rp;
        rp.addRoundedRect(mb.adjusted(0, 0, -0.5, -0.5), 4, 4);
        p.fillPath(rp, hb);
    }
    p.setPen(QPen(theme::Muted, 1.4, Qt::SolidLine, Qt::RoundCap));
    p.drawLine(mb.left() + 6, mb.center().y() + 4,
               mb.right() - 5, mb.center().y() + 4);

    // Resize grip — chevron in the inner corner.
    const QRect grip = resizeGripRect();
    QColor gripCol = theme::Muted; gripCol.setAlpha(180);
    p.setPen(QPen(gripCol, 1.2));
    {
        // Two diagonal strokes forming a chevron pointing into the body.
        const QPoint c = grip.center();
        const int s = 4;
        switch (m_corner) {
        case TopLeft: // grip is SE of body, chevron points NW (outward growth)
            p.drawLine(c.x() - s, c.y(),       c.x(),       c.y() - s);
            p.drawLine(c.x(),     c.y() + s/2, c.x() + s/2, c.y());
            break;
        case TopRight: // grip is SW of body, chevron points NE
            p.drawLine(c.x(), c.y() - s,       c.x() + s, c.y());
            p.drawLine(c.x() - s/2, c.y(),     c.x(),     c.y() + s/2);
            break;
        case BottomLeft: // grip is NE of body, chevron points SW
            p.drawLine(c.x() - s, c.y(),       c.x(),     c.y() + s);
            p.drawLine(c.x(),     c.y() - s/2, c.x() + s/2, c.y());
            break;
        case BottomRight: // grip is NW of body, chevron points SE
        default:
            p.drawLine(c.x(), c.y() + s,       c.x() + s, c.y());
            p.drawLine(c.x() - s/2, c.y(),     c.x(),     c.y() - s/2);
            break;
        }
    }
}

// --------------------------------------------------------------------------
// Mouse handling
// --------------------------------------------------------------------------

void VideoDock::mousePressEvent(QMouseEvent *e)
{
    if (e->button() != Qt::LeftButton) { e->ignore(); return; }

    if (m_minimized) {
        // single-click anywhere on the pill restores
        m_minimized = false;
        reposition();
        writeState();
        update();
        e->accept();
        return;
    }

    const QPoint p = e->pos();
    if (minimizeBtnRect().contains(p)) {
        m_minimized = true;
        reposition();
        writeState();
        update();
        e->accept();
        return;
    }
    if (resizeGripRect().contains(p)) {
        m_action = ActionResize;
        m_pressMouseGlobal = e->globalPosition().toPoint();
        m_pressSize = size();
        m_pressTopLeft = pos();
        e->accept();
        return;
    }
    if (titleBarRect().contains(p)) {
        m_action = ActionDrag;
        m_pressMouseGlobal = e->globalPosition().toPoint();
        m_pressTopLeft = pos();
        raise();
        e->accept();
        return;
    }
    e->ignore();
}

void VideoDock::mouseMoveEvent(QMouseEvent *e)
{
    const QPoint p = e->pos();

    // Hover state for the minimize button (visual feedback).
    if (m_action == ActionNone && !m_minimized) {
        const bool h = minimizeBtnRect().contains(p);
        if (h != m_hoverMinBtn) {
            m_hoverMinBtn = h;
            update();
        }
        // Cursor over interactive zones.
        if (minimizeBtnRect().contains(p)) {
            setCursor(Qt::PointingHandCursor);
        } else if (resizeGripRect().contains(p)) {
            const bool diag1 = (m_corner == TopLeft || m_corner == BottomRight);
            setCursor(diag1 ? Qt::SizeFDiagCursor : Qt::SizeBDiagCursor);
        } else if (titleBarRect().contains(p)) {
            setCursor(Qt::OpenHandCursor);
        } else {
            unsetCursor();
        }
    }

    if (m_action == ActionDrag) {
        const QPoint delta = e->globalPosition().toPoint() - m_pressMouseGlobal;
        const QPoint newTL = m_pressTopLeft + delta;
        move(newTL);
        setCursor(Qt::ClosedHandCursor);
        e->accept();
    } else if (m_action == ActionResize) {
        const QPoint delta = e->globalPosition().toPoint() - m_pressMouseGlobal;
        // Direction of growth depends on which corner the dock is anchored
        // at (and therefore which inner corner holds the grip). Resize
        // keeps the anchored corner fixed in the parent.
        // dirX/dirY translate "delta in screen space" -> "delta in size".
        int dirX = 0, dirY = 0;
        switch (m_corner) {
        case TopLeft:     dirX = +1; dirY = +1; break;
        case TopRight:    dirX = -1; dirY = +1; break;
        case BottomLeft:  dirX = +1; dirY = -1; break;
        case BottomRight: dirX = -1; dirY = -1; break;
        }
        int nw = m_pressSize.width()  + dirX * delta.x();
        int nh = m_pressSize.height() + dirY * delta.y();
        nw = std::clamp(nw, kMinW, kMaxW);
        nh = std::clamp(nh, kMinH, kMaxH);
        // Clamp to parent rect.
        if (parentWidget()) {
            const QRect pr = parentWidget()->rect();
            nw = std::min(nw, pr.width()  - 2 * kInset);
            nh = std::min(nh, pr.height() - 2 * kInset);
        }
        m_size = QSize(nw, nh);
        // Keep the anchored corner fixed -- recompute the top-left.
        const QPoint tl = anchoredTopLeft(m_size);
        setGeometry(QRect(tl, m_size));
        layoutInner();
        update();
        e->accept();
    } else {
        e->ignore();
    }
}

void VideoDock::mouseReleaseEvent(QMouseEvent *e)
{
    if (e->button() != Qt::LeftButton) { e->ignore(); return; }

    if (m_action == ActionDrag) {
        snapToNearestCorner();
        writeState();
        unsetCursor();
        m_action = ActionNone;
        e->accept();
        return;
    }
    if (m_action == ActionResize) {
        writeState();
        m_action = ActionNone;
        e->accept();
        return;
    }
    e->ignore();
}

void VideoDock::resizeEvent(QResizeEvent *)
{
    layoutInner();
}

bool VideoDock::event(QEvent *e)
{
    // Reset hover state when the mouse leaves the widget.
    if (e->type() == QEvent::HoverLeave || e->type() == QEvent::Leave) {
        if (m_hoverMinBtn) { m_hoverMinBtn = false; update(); }
    }
    return QWidget::event(e);
}

// --------------------------------------------------------------------------
// Corner snap + persistence
// --------------------------------------------------------------------------

void VideoDock::snapToNearestCorner()
{
    if (!parentWidget()) return;
    const QRect pr = parentWidget()->rect();
    const QPoint c = geometry().center();
    const bool right  = c.x() > pr.width()  / 2;
    const bool bottom = c.y() > pr.height() / 2;
    m_corner = bottom ? (right ? BottomRight : BottomLeft)
                      : (right ? TopRight    : TopLeft);
    reposition();
}

void VideoDock::writeState() const
{
    QSettings s;
    s.beginGroup(QString::fromLatin1(kSettingsKey));
    s.setValue(QStringLiteral("corner"),    static_cast<int>(m_corner));
    s.setValue(QStringLiteral("w"),         m_size.width());
    s.setValue(QStringLiteral("h"),         m_size.height());
    s.setValue(QStringLiteral("minimized"), m_minimized);
    s.endGroup();
}

void VideoDock::readState()
{
    QSettings s;
    s.beginGroup(QString::fromLatin1(kSettingsKey));
    m_corner = static_cast<Corner>(
        s.value(QStringLiteral("corner"), static_cast<int>(BottomRight)).toInt());
    const int w = s.value(QStringLiteral("w"), m_size.width()).toInt();
    const int h = s.value(QStringLiteral("h"), m_size.height()).toInt();
    m_size = QSize(std::clamp(w, kMinW, kMaxW),
                    std::clamp(h, kMinH, kMaxH));
    m_minimized = s.value(QStringLiteral("minimized"), false).toBool();
    s.endGroup();
}
