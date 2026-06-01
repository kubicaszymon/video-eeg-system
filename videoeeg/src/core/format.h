#pragma once

// Readout formatting, mirroring the design's helpers exactly so the numbers
// on screen match the mockup (disk/sample rates are the design's estimates).

#include <QString>
#include <QTime>
#include <cmath>
#include <cstdint>

namespace fmt {

inline QString elapsed(qint64 ms)
{
    const qint64 s = ms / 1000;
    const qint64 h = s / 3600;
    const qint64 m = (s % 3600) / 60;
    const qint64 sec = s % 60;
    return QStringLiteral("%1:%2:%3")
        .arg(h, 2, 10, QLatin1Char('0'))
        .arg(m, 2, 10, QLatin1Char('0'))
        .arg(sec, 2, 10, QLatin1Char('0'));
}

inline QString clock(const QTime &t)
{
    return QStringLiteral("%1:%2:%3")
        .arg(t.hour(), 2, 10, QLatin1Char('0'))
        .arg(t.minute(), 2, 10, QLatin1Char('0'))
        .arg(t.second(), 2, 10, QLatin1Char('0'));
}

// ~17 KB/s for 32 ch 16-bit @ 500 Hz + 960×720@30 H.264 video (estimate).
inline QString diskMB(qint64 ms)
{
    const qint64 mb = static_cast<qint64>(std::llround(ms * 17.0 / 1024.0));
    return QStringLiteral("%1 MB").arg(mb);
}

inline QString samples(qint64 ms, int sampleRate = 500)
{
    const qint64 n = static_cast<qint64>(std::floor(ms * sampleRate / 1000.0));
    QString digits = QString::number(n);
    for (int i = digits.size() - 3; i > 0; i -= 3)
        digits.insert(i, QLatin1Char(' '));
    return digits;
}

} // namespace fmt
