#pragma once

// VideoDock — floating, draggable, resizable camera dock that overlays
// the EEG canvas in the monitor view. Direct Qt port of the
// "VideoCanvas" floating-dock component from the Claude Design bundle
// (veeg-ui.jsx, "VideoCanvas — floating dock window that overlays the
// EEG area").
//
// Behaviour:
//   - drag by title bar  -> on release, snaps to the nearest corner of
//     its parent (4 corners: TL / TR / BL / BR)
//   - resize from inner corner (opposite the dock corner) -> grow / shrink
//   - minimise button   -> collapse to a small "Camera HH:MM:SS" pill
//   - state persisted via QSettings (corner, size, minimised, last
//     restored size)
//
// The actual video frame painting is delegated to the existing
// VideoCanvas, which is embedded as a child and positioned inside the
// body rect. VideoDock paints its own title bar / chrome / REC badge.

#include <QPoint>
#include <QSize>
#include <QString>
#include <QWidget>

class VideoCanvas;
class LslVideoReceiver;

class VideoDock : public QWidget
{
    Q_OBJECT
public:
    enum Corner { TopLeft, TopRight, BottomLeft, BottomRight };

    explicit VideoDock(QWidget *parent = nullptr);
    ~VideoDock() override;

    // Proxied through to the inner VideoCanvas / dock title bar.
    void setRecording(bool on);
    void setTimecode(const QString &tc);
    void setReceiver(LslVideoReceiver *recv);

    // Recompute own geometry from corner + size (or pill geometry if
    // minimised). Call this from the parent widget's resizeEvent and any
    // time corner/size/minimised changes.
    void reposition();

protected:
    void paintEvent(QPaintEvent *) override;
    void mousePressEvent(QMouseEvent *) override;
    void mouseMoveEvent(QMouseEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;
    void resizeEvent(QResizeEvent *) override;
    bool event(QEvent *) override;     // for cursor updates on hover

private:
    // Geometry helpers (in widget-local coordinates).
    QRect titleBarRect()   const;
    QRect bodyRect()       const;
    QRect resizeGripRect() const;
    QRect minimizeBtnRect() const;
    QRect pillRect()       const;       // when minimized

    // Geometry helpers (in parent coordinates).
    QPoint anchoredTopLeft(QSize sz) const;   // for current corner

    void snapToNearestCorner();         // after drag release
    void layoutInner();                 // place VideoCanvas + raise
    void writeState() const;
    void readState();

    VideoCanvas *m_canvas = nullptr;

    Corner  m_corner    = BottomRight;
    QSize   m_size      = QSize(380, 285);  // 4:3-ish default
    bool    m_minimized = false;
    QString m_timecode  = QStringLiteral("Live");
    bool    m_recording = false;

    // Mouse action state.
    enum Action { ActionNone, ActionDrag, ActionResize };
    Action m_action = ActionNone;
    QPoint m_pressMouseGlobal;
    QPoint m_pressTopLeft;
    QSize  m_pressSize;
    bool   m_hoverMinBtn = false;
};
