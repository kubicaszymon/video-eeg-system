#pragma once

// Plain-data model shared across the UI. No streams yet - synthetic only.

#include <QString>
#include <QVector>
#include <cstdint>

enum class Screen {
    Welcome,
    Preview,
    Recording,
};

struct Session {
    QString subject;
    QString op;             // operator
    QString filename;
    QString notes;
    QString startedAtClock; // wall-clock "HH:MM:SS" when recording began
};

struct Marker {
    int     id        = 0;
    qint64  elapsedMs  = 0;
    QString label;
};

struct Filters {
    double hp    = 0.5;   // high-pass, Hz
    double lp    = 70.0;  // low-pass, Hz   (0 == off)
    double notch = 50.0;  // notch, Hz      (0 == off)
};

struct Device {
    QString label;
    QString sub;
};

// Real hardware — hardware is fixed; no device-selection UI needed.
struct Devices {
    Device amp     {QStringLiteral("BrainTech Perun32"),      QStringLiteral("32 ch · 500 Hz")};
    Device camera  {QStringLiteral("Raspberry Pi Camera v1"), QStringLiteral("960×720 · 30 fps · H.264")};
    Device storage {QStringLiteral("recordings\\"),           QStringLiteral("")};
};
