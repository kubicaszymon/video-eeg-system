#pragma once

#include <QPointF>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QTimer;
class QElapsedTimer;
class LslEegReceiver;
class LslVideoReceiver;
class VideoDock;

// ---------------------------------------------------------------------------
// EegCanvas: panel with 8 synthetic scrolling traces. The waveform formula is
// ported from the design's makeTrace() so it looks identical to the mockup.
// Traces are white in preview, accent-coloured (with a soft glow) while
// recording. Rendering is fully custom-painted for performance: per-channel
// sample tables are rebuilt only on resize; each frame just maps + clips them.
// ---------------------------------------------------------------------------
class EegCanvas : public QWidget
{
    Q_OBJECT
public:
    explicit EegCanvas(QWidget *parent = nullptr);

    void setRecording(bool on);

    // Attach a live LSL receiver. When attached *and* connected, paintEvent
    // draws real samples (subset of signal channels) instead of the mock
    // sine waves. Pass nullptr to detach. Safe to call any time.
    void setReceiver(LslEegReceiver *recv);

protected:
    void paintEvent(QPaintEvent *) override;
    void resizeEvent(QResizeEvent *) override;
    void showEvent(QShowEvent *) override;
    void hideEvent(QHideEvent *) override;

private:
    QRect traceAreaRect() const;
    void rebuildSamples();

    struct Sample { float x; float v; };          // x in px, v normalised
    QVector<QVector<Sample>> m_channels;          // [8][n] -- mock data
    bool m_recording = false;
    int m_headerH = 41;
    int m_labelW  = 56;

    QTimer *m_timer = nullptr;
    QElapsedTimer *m_clock = nullptr;

    // Real-data path (used when m_receiver is set + connected).
    LslEegReceiver *m_receiver = nullptr;
    QStringList     m_realLabels;    // dynamic; from receiver metadata

public:
    // Attach a floating VideoDock that overlays the EEG area. The dock is
    // re-parented to this canvas and repositioned whenever the canvas
    // resizes. Pass nullptr to detach.
    void setVideoDock(VideoDock *dock);
private:
    VideoDock *m_videoDock = nullptr;
};

// ---------------------------------------------------------------------------
// VideoCanvas: fixed-width panel. Black feed area with a diagonally hatched
// "camera feed" placeholder (no real stream yet) and a blinking REC badge
// while recording.
// ---------------------------------------------------------------------------
class VideoCanvas : public QWidget
{
    Q_OBJECT
public:
    explicit VideoCanvas(QWidget *parent = nullptr);

    void setRecording(bool on);

    // Attach a live LSL video receiver. When attached + connected + has a
    // decoded frame, paintEvent draws it into the feed area; otherwise
    // falls back to the placeholder graphic. Safe to call any time.
    void setReceiver(LslVideoReceiver *recv);

protected:
    void paintEvent(QPaintEvent *) override;

private:
    bool m_recording = false;
    bool m_blinkOn = true;
    QTimer *m_blink = nullptr;

    LslVideoReceiver *m_receiver = nullptr;
};
