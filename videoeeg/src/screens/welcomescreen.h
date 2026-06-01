#pragma once

#include "appmodel.h"

#include <QFrame>
#include <QWidget>

class QLabel;

// A single "device" card on the welcome screen — shows a status dot,
// the device name and its spec subtitle. Read-only: hardware is fixed.
class DeviceCard : public QFrame
{
    Q_OBJECT
public:
    DeviceCard(const QString &caption, QWidget *parent = nullptr);

    void setDevice(const Device &d);

private:
    QLabel *m_value = nullptr;
    QLabel *m_sub = nullptr;
};

// Minimal launch screen: brand bar, three device cards, one Start button.
class WelcomeScreen : public QWidget
{
    Q_OBJECT
public:
    explicit WelcomeScreen(QWidget *parent = nullptr);

    void setDevices(const Devices &d);

signals:
    void startRequested();

private:
    DeviceCard *m_amp = nullptr;
    DeviceCard *m_camera = nullptr;
    DeviceCard *m_storage = nullptr;
};
