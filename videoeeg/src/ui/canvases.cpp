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
#include <cmath>
#include <cstdint>
#include <random>
#include <utility>
#include <vector>

namespace {

constexpr int kChannels = 32;   // matches the BrainTech Perun32 channel count
const std::array<const char *, kChannels> kLabels = {
    "Fp1", "Fp2", "AF3", "AF4", "F7",  "F3",  "Fz",  "F4",
    "F8",  "FC5", "FC1", "FC2", "FC6", "T7",  "C3",  "Cz",
    "C4",  "T8",  "CP5", "CP1", "CP2", "CP6", "P7",  "P3",
    "Pz",  "P4",  "P8",  "PO3", "PO4", "O1",  "Oz",  "O2"};

constexpr double kSampleStepPx = 3.0;
constexpr double kScrollPeriodMs = 9000.0; // one tile-width per 9 s
constexpr double kAmpFraction = 0.42;      // matches design makeTrace amp

// Realistic synthetic EEG, used only as the offline fallback (no hardware) —
// e.g. for thesis screenshots/figures. Built from filtered Gaussian noise (so it
// looks like a real recording, not smooth sines): a 1/f-ish background, a
// posterior-dominant alpha rhythm that waxes and wanes, plus *localised*
// artifacts — frontal eye blinks, temporal muscle bursts, and occasional
// single-channel electrode pops. No synchronous whole-head transients. The
// per-channel assembly lives in EegCanvas::rebuildSamples().

// 10-20 region of a channel: 0 frontal-pole, 1 fronto-central, 2 frontal,
// 3 temporal, 4 central, 5 parietal, 6 occipital.
int regionOf(int channel)
{
    const char *l = kLabels[channel];
    if ((l[0] == 'F' && l[1] == 'p') || (l[0] == 'A' && l[1] == 'F')) return 0;
    if (l[0] == 'F' && l[1] == 'C') return 1;
    if (l[0] == 'F')                return 2;
    if (l[0] == 'T')                return 3;
    if (l[0] == 'C')                return 4;   // C* and CP*
    if (l[0] == 'P')                return 5;   // P* and PO*
    return 6;                                    // O*
}

// Pink-ish (1/f) background: sum of AR(1) leaky integrators of white noise over
// octave time-constants, weighted ~sqrt(tau). Returned unit-variance.
std::vector<double> genPink(int n, std::mt19937 &rng)
{
    std::normal_distribution<double> N(0.0, 1.0);
    std::vector<double> out(n, 0.0);
    static const double fr[6] = {0.0015, 0.003, 0.006, 0.0125, 0.025, 0.05};
    for (double f : fr) {
        const double tau = std::max(2.0, f * n);
        const double a = std::exp(-1.0 / tau), b = 1.0 - a, wgt = std::sqrt(tau);
        double prev = 0.0;
        for (int i = 0; i < n; ++i) { prev = a * prev + b * N(rng); out[i] += wgt * prev; }
    }
    double m = 0.0; for (double v : out) m += v; m /= n;
    double s = 0.0; for (double v : out) s += (v - m) * (v - m);
    s = std::sqrt(s / n) + 1e-9;
    for (double &v : out) v = (v - m) / s;
    return out;
}

// Narrow-band oscillation (a 2-pole resonator driven by white noise) at fa
// cycles/sample — used for the alpha rhythm and muscle bursts. Unit-variance.
std::vector<double> genReson(int n, double fa, double r, std::mt19937 &rng)
{
    std::normal_distribution<double> N(0.0, 1.0);
    const double w0 = 2.0 * M_PI * fa, bb = 2.0 * r * std::cos(w0), cc = -r * r;
    std::vector<double> o(n);
    double y1 = 0.0, y2 = 0.0;
    for (int i = 0; i < n; ++i) { double y = bb * y1 + cc * y2 + N(rng); o[i] = y; y2 = y1; y1 = y; }
    double s = 0.0; for (double v : o) s += v * v; s = std::sqrt(s / n) + 1e-9;
    for (double &v : o) v /= s;
    return o;
}

// Slow random amplitude envelope in ~[0.35, 1.05] (for alpha waxing / waning).
std::vector<double> slowEnv(int n, double frac, std::mt19937 &rng)
{
    std::normal_distribution<double> N(0.0, 1.0);
    const double tau = std::max(2.0, frac * n), a = std::exp(-1.0 / tau), b = 1.0 - a;
    std::vector<double> y(n);
    double prev = 0.0;
    for (int i = 0; i < n; ++i) { prev = a * prev + b * N(rng); y[i] = prev; }
    double s = 0.0; for (double v : y) s += v * v; s = std::sqrt(s / n) + 1e-9;
    for (double &v : y) v = 0.35 + 0.7 * (0.5 + 0.5 * std::tanh(1.3 * v / s));
    return y;
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
    const int n = static_cast<int>((2.0 * w) / kSampleStepPx) + 2;

    // Per-region weights: 0 fp, 1 fc, 2 f, 3 t, 4 c, 5 p, 6 o.
    static const double kAlphaGain[7] = {0.05, 0.18, 0.10, 0.20, 0.35, 0.78, 1.00};
    static const double kBlinkGain[7] = {1.00, 0.18, 0.42, 0.00, 0.00, 0.00, 0.00};

    // Eye blinks are (near-)synchronous across the frontal field -> shared times.
    std::mt19937 master(20260603u);
    std::uniform_int_distribution<int> Upos(0, std::max(0, n - 1));
    const int nBlink = std::max(2, n / 420);
    std::vector<int> blinkAt(nBlink);
    for (int &bt : blinkAt) bt = Upos(master);

    for (int ch = 0; ch < kChannels; ++ch) {
        const int r = regionOf(ch);
        std::mt19937 rng(1000u + static_cast<unsigned>(ch));
        std::uniform_real_distribution<double> U(0.0, 1.0);
        std::uniform_int_distribution<int> Up(0, std::max(0, n - 1));

        std::vector<double> sig = genPink(n, rng);
        for (double &v : sig) v *= 0.9;

        // posterior-dominant alpha, amplitude waxing / waning
        if (kAlphaGain[r] > 0.06) {
            const double fa = 0.05 + (U(rng) - 0.5) * 0.008;   // ~10 Hz, slight wobble
            const std::vector<double> env = slowEnv(n, 0.13, rng);
            const std::vector<double> al = genReson(n, fa, 0.986, rng);
            for (int i = 0; i < n; ++i) sig[i] += kAlphaGain[r] * 1.05 * env[i] * al[i];
        }

        // frontal eye blinks (synchronous; weighted by region)
        if (kBlinkGain[r] > 0.0) {
            const double wdt = 0.02 * n;
            for (int bt : blinkAt)
                for (int i = 0; i < n; ++i) {
                    const double d = (i - bt) / wdt;
                    sig[i] += kBlinkGain[r] * 4.5 * std::exp(-d * d) * (1.0 - (d / 2.6) * (d / 2.6));
                }
        }

        // temporal (and lateral-frontal) muscle bursts
        const bool lateralF = (r == 2 && (kLabels[ch][1] == '7' || kLabels[ch][1] == '8'));
        if (r == 3 || lateralF) {
            const int bursts = 1 + static_cast<int>(U(rng) * 2.0);   // 1 or 2
            for (int j = 0; j < bursts; ++j) {
                const int c0 = Up(rng);
                const std::vector<double> mb = genReson(n, 0.22, 0.9, rng);
                const double amp = (r == 3) ? 0.7 : 0.4, ew = 0.05 * n;
                for (int i = 0; i < n; ++i) {
                    const double e = std::exp(-((i - c0) / ew) * ((i - c0) / ew));
                    sig[i] += amp * e * mb[i];
                }
            }
        }

        // occasional single-channel electrode pop / movement transient
        if (U(rng) < 0.18) {
            const int c0 = Up(rng);
            const double sgn = (U(rng) < 0.5) ? 1.0 : -1.0;
            for (int i = c0; i < n; ++i) sig[i] += sgn * 5.0 * std::exp(-(i - c0) / 22.0);
        }

        // normalize so channels display at a comparable gain (95th percentile);
        // large artifacts deliberately overflow into neighbours, as on real EEG.
        std::vector<double> mag(n);
        for (int i = 0; i < n; ++i) mag[i] = std::fabs(sig[i]);
        const int q = std::min(n - 1, static_cast<int>(0.95 * n));
        std::nth_element(mag.begin(), mag.begin() + q, mag.end());
        const double p95 = mag[q] + 1e-9;

        auto &col = m_channels[ch];
        col.resize(n);
        for (int k = 0; k < n; ++k)
            col[k] = {static_cast<float>(k * kSampleStepPx),
                      static_cast<float>(sig[k] / p95)};
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
    const QString titleText =
        QStringLiteral("EEG · %1 channels").arg(useReal ? nRows : kChannels);
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
