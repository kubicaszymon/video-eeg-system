#include "canvases.h"
#include "lsleegreceiver.h"
#include "lslvideoreceiver.h"
#include "theme.h"
#include "videodock.h"

#include <QElapsedTimer>
#include <QPainter>
#include <QPainterPath>
#include <QPaintEvent>
#include <QTimer>
#include <QtMath>

#include <algorithm>
#include <array>

namespace {

constexpr int kChannels = 8;
const std::array<const char *, kChannels> kLabels = {
    "Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"};

constexpr double kSampleStepPx = 3.0;
constexpr double kScrollPeriodMs = 9000.0; // one tile-width per 9 s
constexpr double kAmpFraction = 0.42;      // matches design makeTrace amp

double traceValue(int channel, double t)
{
    const double seed = channel * 13.0 + 5.0;
    const double w = 2.0 * M_PI;
    double v = std::sin(t * w * 3.0  + seed)        * 0.30
             + std::sin(t * w * 7.0  + seed * 2.0)  * 0.18
             + std::sin(t * w * 11.0 + seed * 0.7)  * 0.32
             + std::sin(t * w * 19.0 + seed * 1.3)  * 0.10;
    if (channel == 0 || channel == 1) {
        double phase = std::fmod(t - 0.62 + 1.0, 1.0);
        double dist = std::min(phase, 1.0 - phase);
        v += std::exp(-dist * dist * 1200.0) * 0.9;
    }
    return v;
}

} // namespace

// ============================== EegCanvas =================================

EegCanvas::EegCanvas(QWidget *parent)
    : QWidget(parent)
{
    setAttribute(Qt::WA_OpaquePaintEvent);
    m_channels.resize(kChannels);
    m_clock = new QElapsedTimer;
    m_clock->start();
    m_timer = new QTimer(this);
    m_timer->setInterval(16); // ~60 fps
    connect(m_timer, &QTimer::timeout, this,
            qOverload<>(&QWidget::update));
}

void EegCanvas::setRecording(bool on)
{
    if (m_recording == on)
        return;
    m_recording = on;
    update();
}

void EegCanvas::setReceiver(LslEegReceiver *recv)
{
    if (m_receiver == recv)
        return;
    if (m_receiver)
        m_receiver->disconnect(this);
    m_receiver = recv;
    if (m_receiver) {
        // chunkReceived is emitted from the receiver's QThread; Qt's queued
        // connection automatically hops it onto our GUI thread for update().
        connect(m_receiver, &LslEegReceiver::chunkReceived,
                this,       qOverload<>(&QWidget::update));
        connect(m_receiver, &LslEegReceiver::streamResolved,
                this,       qOverload<>(&QWidget::update));
        connect(m_receiver, &LslEegReceiver::streamLost,
                this,       qOverload<>(&QWidget::update));
        // Real data drives paints now -- stop the 60 Hz mock-scroll timer.
        // Without this, paint events pile up at 60 Hz on top of every
        // chunkReceived, the GUI thread stays glued to painting, and the
        // app feels frozen (1-2 fps) during recording with 32 channels.
        if (m_timer) m_timer->stop();
    } else {
        // No receiver -- mock scroll wants the 60 Hz timer again.
        if (m_timer && isVisible()) m_timer->start();
    }
    update();
}

QRect EegCanvas::traceAreaRect() const
{
    return QRect(m_labelW, m_headerH,
                 width() - m_labelW, height() - m_headerH);
}

void EegCanvas::rebuildSamples()
{
    const double w = std::max(1, traceAreaRect().width());
    const int count = static_cast<int>((2.0 * w) / kSampleStepPx) + 2;
    for (int ch = 0; ch < kChannels; ++ch) {
        auto &col = m_channels[ch];
        col.resize(count);
        for (int k = 0; k < count; ++k) {
            const double x = k * kSampleStepPx;
            const double t = x / w;
            col[k] = {static_cast<float>(x),
                      static_cast<float>(traceValue(ch, t))};
        }
    }
}

void EegCanvas::resizeEvent(QResizeEvent *)
{
    rebuildSamples();
    if (m_videoDock)
        m_videoDock->reposition();
}

void EegCanvas::setVideoDock(VideoDock *dock)
{
    m_videoDock = dock;
    if (m_videoDock) {
        m_videoDock->setParent(this);
        m_videoDock->reposition();
        m_videoDock->raise();
        m_videoDock->show();
    }
}

void EegCanvas::showEvent(QShowEvent *)
{
    if (m_channels.isEmpty() || m_channels[0].isEmpty())
        rebuildSamples();
    // Only run the 60 Hz mock-scroll timer when a receiver isn't attached.
    // With a live receiver, chunkReceived drives the paints; running both
    // wastes paint cycles + drags fps down (see setReceiver()).
    if (!m_receiver)
        m_timer->start();
}

void EegCanvas::hideEvent(QHideEvent *)
{
    m_timer->stop();
}

void EegCanvas::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    const QRectF full(0.5, 0.5, width() - 1.0, height() - 1.0);
    QPainterPath panel;
    panel.addRoundedRect(full, theme::Radius, theme::Radius);
    p.setClipPath(panel);

    p.fillRect(rect(), theme::Panel);

    // ---- decide mock vs real ---------------------------------------------
    // Pull the receiver snapshot once up front. If unreachable / not yet
    // connected / no samples, fall through to the synthetic-sine fallback so
    // the canvas always shows *something* (useful when the Pi is offline).
    const bool                 hasReceiver = (m_receiver != nullptr);
    LslEegReceiver::Info       recvInfo;
    LslEegReceiver::Snapshot   snap;
    QVector<int>               visChannels;       // ALL signal channels
    QStringList                visLabels;
    if (hasReceiver) {
        recvInfo = m_receiver->info();
        snap     = m_receiver->snapshot();
        // Show every signal channel (e.g. 32 for Perun32). Impedance channels
        // are excluded; they live in recvInfo.impedanceIdx.
        for (int idx : recvInfo.signalIdx) {
            visChannels.append(idx);
            visLabels << recvInfo.channels.value(idx).label;
        }
    }
    const bool useReal = hasReceiver && m_receiver->connected()
                         && !visChannels.isEmpty() && snap.frames > 0;
    // Number of rows the trace area will draw -- dynamic in real mode,
    // fixed-at-8 mock fallback otherwise.
    const int nRows = useReal ? visChannels.size() : kChannels;

    // ---- header ----------------------------------------------------------
    QFont title(theme::uiFontFamily());
    title.setPixelSize(13);
    title.setWeight(QFont::DemiBold);
    p.setFont(title);
    p.setPen(theme::Text);
    const QString titleText = useReal
        ? QStringLiteral("EEG · %1 channels").arg(nRows)
        : QStringLiteral("EEG · 8 channels");
    p.drawText(QRect(18, 0, width(), m_headerH),
               Qt::AlignVCenter | Qt::AlignLeft, titleText);
    const int titleW = QFontMetrics(title).horizontalAdvance(titleText);

    QFont info(theme::monoFontFamily());
    info.setPixelSize(11);
    p.setFont(info);
    p.setPen(theme::Muted);
    QString rateText;
    if (useReal) {
        rateText = QString::asprintf("%.0f Hz · 10 s window",
                                      recvInfo.nominalSrate);
    } else if (hasReceiver && !m_receiver->connected()) {
        rateText = QStringLiteral("connecting…");
    } else {
        rateText = QStringLiteral("500 Hz · 10 s window");
    }
    p.drawText(QRect(18 + titleW + 14, 0, width(), m_headerH),
               Qt::AlignVCenter | Qt::AlignLeft, rateText);

    QFont smol(theme::uiFontFamily());
    smol.setPixelSize(11);
    p.setFont(smol);
    p.drawText(QRect(0, 0, width() - 18, m_headerH),
               Qt::AlignVCenter | Qt::AlignRight,
               QStringLiteral("50 μV/div"));

    p.setPen(theme::Border);
    p.drawLine(0, m_headerH, width(), m_headerH);

    // ---- label column ----------------------------------------------------
    const QRect area = traceAreaRect();
    const double rowH = area.height() / static_cast<double>(nRows);
    // Scale label font down when there are many channels so they still fit.
    // 8 ch -> 11 px, 32 ch -> ~9 px, clamped to [8, 11].
    const int labelPx = std::clamp(static_cast<int>(rowH * 0.5), 8, 11);
    QFont chFont(theme::monoFontFamily());
    chFont.setPixelSize(labelPx);
    p.setFont(chFont);
    for (int i = 0; i < nRows; ++i) {
        const double top = area.top() + i * rowH;
        p.setPen(theme::Muted);
        const QString label = useReal && i < visLabels.size()
                                  ? visLabels[i]
                                  : QString::fromLatin1(kLabels[i % kChannels]);
        p.drawText(QRectF(14, top, m_labelW - 14, rowH),
                   Qt::AlignVCenter | Qt::AlignLeft, label);
        // Only draw row separators for sparse layouts; with 32 rows they
        // become visual noise.
        if (i < nRows - 1 && nRows <= 12) {
            p.setPen(theme::Border);
            p.drawLine(QPointF(0, top + rowH), QPointF(m_labelW, top + rowH));
        }
    }
    p.setPen(theme::Border);
    p.drawLine(m_labelW, m_headerH, m_labelW, height());

    // ---- trace area ------------------------------------------------------
    p.fillRect(area, theme::TraceArea);
    p.save();
    p.setClipRect(area);

    p.setPen(QPen(theme::Border, 1));
    for (int s = 1; s <= 9; ++s) {
        const double gx = area.left() + (s / 10.0) * area.width();
        p.drawLine(QPointF(gx, area.top()), QPointF(gx, area.bottom()));
    }
    // Per-channel center lines (the dim horizontal zero-line). Skip for
    // dense layouts where they'd become visual noise.
    if (nRows <= 12) {
        for (int i = 0; i < nRows; ++i) {
            const double cy = area.top() + i * rowH + rowH / 2.0;
            p.drawLine(QPointF(area.left(), cy), QPointF(area.right(), cy));
        }
    }

    const QColor traceColor = m_recording ? theme::Accent : theme::Text;

    if (useReal) {
        // Time-mapped polylines from the LSL ring buffer.
        // 10 s window ending at the newest sample's timestamp.
        constexpr double kWindowSec = 10.0;
        const double tMax = snap.timestamps[snap.frames - 1];
        const double tMin = tMax - kWindowSec;

        // Find the first sample in the visible window.
        int firstK = 0;
        while (firstK < snap.frames && snap.timestamps[firstK] < tMin)
            ++firstK;
        const int nVisible = snap.frames - firstK;

        if (nVisible > 0) {
            // Dense layout (e.g. 32 channels): drop the antialiasing + glow
            // passes during the polyline draw. Each glow pen is a 3 px
            // semi-transparent line on top of every channel, and AA on
            // 32 x several-thousand-vertex polylines is the single biggest
            // CPU sink. At 20-30 px per row the glow + AA effect is also
            // visually muddy, so we trade them away for a smooth ~30 fps.
            const bool dense = nRows > 12;

            // Stride-downsample to ~2 vertices per pixel column. At 500 Hz
            // and a ~700 px-wide trace area, that's ~1400 vertices per
            // channel vs ~5000 raw -- ~3.5x fewer line segments to draw,
            // visually indistinguishable on screen.
            const int targetVerts = std::max(64,
                                              traceAreaRect().width() * 2);
            const int stride = std::max(1, nVisible / targetVerts);

            // Pass 1: per-channel DC offset (mean) and a *robust* amplitude.
            // Auto-scale each channel to fit ~90% of its row -- handles raw
            // amplifier output (huge DC offsets, saturated channels, µV vs
            // mV mismatches) without a hardcoded scale.
            //
            // We deliberately do NOT use the max absolute deviation: a single
            // ~1 s spike (movement, electrode pop) would inflate the scale for
            // the whole 10 s window and keep low signal squashed long after
            // the spike is gone. Instead we take a high percentile (~95th) of
            // |deviation| per channel, so brief spikes simply clip to the row
            // (the clamp below) while the display tracks the bulk amplitude
            // and recovers as soon as the spike scrolls out of the window.
            const int nVis = visChannels.size();
            QVector<double> mean(nVis, 0.0);
            int nForStats = 0;
            for (int k = firstK; k < snap.frames; k += stride) {
                for (int i = 0; i < nVis; ++i) {
                    mean[i] += snap.samples[
                        static_cast<size_t>(k) * snap.channels + visChannels[i]];
                }
                ++nForStats;
            }
            if (nForStats > 0) {
                for (int i = 0; i < nVis; ++i)
                    mean[i] /= nForStats;
            }
            // Collect per-channel |deviation| samples, then take the 95th
            // percentile via nth_element (O(n) partial sort, no full sort).
            QVector<float> scaleDev(nVis, 0.0f);
            {
                QVector<QVector<float>> devs(nVis);
                for (int i = 0; i < nVis; ++i)
                    devs[i].reserve(nForStats);
                for (int k = firstK; k < snap.frames; k += stride) {
                    for (int i = 0; i < nVis; ++i) {
                        const float dev = std::abs(
                            snap.samples[static_cast<size_t>(k) * snap.channels
                                         + visChannels[i]]
                            - static_cast<float>(mean[i]));
                        devs[i].push_back(dev);
                    }
                }
                for (int i = 0; i < nVis; ++i) {
                    auto& d = devs[i];
                    if (d.isEmpty()) continue;
                    const int idx = std::min<int>(
                        d.size() - 1,
                        static_cast<int>(d.size() * 0.95));
                    std::nth_element(d.begin(), d.begin() + idx, d.end());
                    scaleDev[i] = d[idx];
                }
            }
            const double halfRowPx = rowH * 0.45;     // leave 10% margin

            // Pass 2: build + draw each channel's polyline.
            if (dense)
                p.setRenderHint(QPainter::Antialiasing, false);
            for (int i = 0; i < nVis; ++i) {
                const int ch = visChannels[i];
                const double cy = area.top() + i * rowH + rowH / 2.0;
                const double scaleY = (scaleDev[i] > 1e-6f)
                                          ? (halfRowPx / scaleDev[i])
                                          : 0.0;
                QPolygonF poly;
                poly.reserve(nVisible / stride + 2);
                for (int k = firstK; k < snap.frames; k += stride) {
                    const double t = snap.timestamps[k];
                    const double x =
                        area.left() + (t - tMin) / kWindowSec * area.width();
                    const double v = snap.samples[
                        static_cast<size_t>(k) * snap.channels + ch]
                        - mean[i];
                    // Defensive clamp -- if a single sample is wildly off
                    // (e.g. NaN, electrode disconnect spike), keep the line
                    // inside the channel row.
                    double y = cy - v * scaleY;
                    if (y < cy - halfRowPx) y = cy - halfRowPx;
                    if (y > cy + halfRowPx) y = cy + halfRowPx;
                    poly << QPointF(x, y);
                }
                if (m_recording && !dense) {
                    QColor glow = theme::Accent;
                    glow.setAlpha(70);
                    p.setPen(QPen(glow, 3.0));
                    p.drawPolyline(poly);
                }
                p.setPen(QPen(traceColor, 1.0));
                p.drawPolyline(poly);
            }
            if (dense)
                p.setRenderHint(QPainter::Antialiasing, true);
        }
    } else {
        // Mock fallback: existing pixel-scrolled synthetic traces.
        const double scroll = std::fmod(
            m_clock->elapsed() / kScrollPeriodMs, 1.0) * area.width();
        for (int i = 0; i < kChannels; ++i) {
            const auto &col = m_channels[i];
            if (col.isEmpty()) continue;
            const double cy = area.top() + i * rowH + rowH / 2.0;
            QPolygonF poly;
            poly.reserve(col.size());
            for (const auto &s : col) {
                poly << QPointF(area.left() + s.x - scroll,
                                cy - s.v * rowH * kAmpFraction);
            }
            if (m_recording) {
                QColor glow = theme::Accent;
                glow.setAlpha(70);
                p.setPen(QPen(glow, 3.0));
                p.drawPolyline(poly);
            }
            p.setPen(QPen(traceColor, 1.0));
            p.drawPolyline(poly);
        }
    }
    p.restore();
}

// ============================== VideoCanvas ===============================

VideoCanvas::VideoCanvas(QWidget *parent)
    : QWidget(parent)
{
    // No setFixedWidth -- now embedded inside VideoDock, which sizes us.
    setAttribute(Qt::WA_OpaquePaintEvent);
    m_blink = new QTimer(this);
    m_blink->setInterval(600);
    connect(m_blink, &QTimer::timeout, this, [this] {
        m_blinkOn = !m_blinkOn;
        if (m_recording)
            update();
    });
}

void VideoCanvas::setRecording(bool on)
{
    if (m_recording == on)
        return;
    m_recording = on;
    m_blinkOn = true;
    if (on)
        m_blink->start();
    else
        m_blink->stop();
    update();
}

void VideoCanvas::setReceiver(LslVideoReceiver *recv)
{
    if (m_receiver == recv) return;
    if (m_receiver) m_receiver->disconnect(this);
    m_receiver = recv;
    if (m_receiver) {
        // frameReady fires from the decoder QThread; AutoConnection -> Queued
        // so update() runs on the GUI thread.
        connect(m_receiver, &LslVideoReceiver::frameReady,
                this,       qOverload<>(&QWidget::update));
        connect(m_receiver, &LslVideoReceiver::streamResolved,
                this,       qOverload<>(&QWidget::update));
        connect(m_receiver, &LslVideoReceiver::streamLost,
                this,       qOverload<>(&QWidget::update));
    }
    update();
}

void VideoCanvas::paintEvent(QPaintEvent *)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    // The canvas is now embedded inside VideoDock; the dock owns chrome
    // (rounded card + title bar + timecode). We just fill the body with
    // black and paint the decoded frame (or placeholder), plus the REC
    // overlay badge in the top-left of the body.
    const QRect body = rect();
    p.fillRect(body, QColor(0, 0, 0));

    // If we have a decoded frame, draw it scaled to fit (preserving aspect
    // ratio, letterboxed). Otherwise show the placeholder graphic.
    QImage frame;
    if (m_receiver) frame = m_receiver->latestFrame();

    if (!frame.isNull()) {
        const double iw = frame.width();
        const double ih = frame.height();
        const double bw = body.width();
        const double bh = body.height();
        const double scale = std::min(bw / iw, bh / ih);
        const double dw = iw * scale;
        const double dh = ih * scale;
        const QRectF target(body.left() + (bw - dw) / 2.0,
                            body.top()  + (bh - dh) / 2.0,
                            dw, dh);
        // SmoothTransformation is bilinear-ish in Qt; small CPU hit, much
        // better when we scale 960x720 down to a ~520x... viewport.
        p.setRenderHint(QPainter::SmoothPixmapTransform, true);
        p.drawImage(target, frame);
    } else {
        // striped placeholder rectangle
        QRectF ph(0, 0, body.width() * 0.72, body.height() * 0.30);
        ph.moveCenter(QPointF(body.center()));
        QPainterPath phPath;
        phPath.addRoundedRect(ph, 6, 6);
        p.save();
        p.setClipPath(phPath);
        p.fillRect(ph, QColor(0x0a, 0x0a, 0x0a));
        p.setPen(QPen(QColor(0x14, 0x14, 0x14), 6));
        for (double d = -ph.height(); d < ph.width() + ph.height(); d += 14.0) {
            p.drawLine(QPointF(ph.left() + d, ph.top()),
                       QPointF(ph.left() + d - ph.height(), ph.bottom()));
        }
        p.restore();

        QFont feed(theme::monoFontFamily());
        feed.setPixelSize(11);
        feed.setLetterSpacing(QFont::AbsoluteSpacing, 2.0);
        p.setFont(feed);
        p.setPen(QColor(0x55, 0x55, 0x55));
        const QString phLabel = (m_receiver && !m_receiver->connected())
            ? QStringLiteral("connecting…")
            : QStringLiteral("camera feed");
        p.drawText(ph, Qt::AlignCenter, phLabel);
    }

    // ---- REC badge ----
    if (m_recording) {
        QFont rec(theme::uiFontFamily());
        rec.setPixelSize(10);
        rec.setWeight(QFont::DemiBold);
        rec.setLetterSpacing(QFont::AbsoluteSpacing, 1.0);
        p.setFont(rec);
        const QString label = QStringLiteral("REC");
        const int textW = QFontMetrics(rec).horizontalAdvance(label);
        const QRectF badge(body.left() + 14, body.top() + 14,
                           textW + 38, 24);
        QPainterPath bp;
        bp.addRoundedRect(badge, badge.height() / 2.0, badge.height() / 2.0);
        p.fillPath(bp, QColor(0, 0, 0, 140));
        QColor bd = theme::Danger;
        bd.setAlpha(102);
        p.setPen(QPen(bd, 1));
        p.drawPath(bp);
        if (m_blinkOn) {
            p.setBrush(theme::Danger);
            p.setPen(Qt::NoPen);
            p.drawEllipse(QPointF(badge.left() + 16, badge.center().y()), 3.5, 3.5);
        }
        p.setPen(theme::Danger);
        p.drawText(QRectF(badge.left() + 26, badge.top(),
                          badge.width() - 30, badge.height()),
                   Qt::AlignVCenter | Qt::AlignLeft, label);
    }
}
