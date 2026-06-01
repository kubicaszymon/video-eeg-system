#pragma once

// VideoControlDock — QDockWidget for remote-controlling the Video Pi
// (picam-control.service, port 8081). Mirrors the video dock panel in
// pi_camera/pc_app/sync_prototype.py.
//
// Same pattern as EegControlDock: binds to a PiControlPoller, reads its
// cached snapshot on snapshotChanged(), sends control requests via
// poller->sendControl(). Video kind has no /channels or /impedance — those
// endpoints return 404 on the video Pi.

#include <QDockWidget>
#include <QJsonObject>     // moc needs the full type for the slots below

class PiControlPoller;
class QCheckBox;
class QComboBox;
class QGroupBox;
class QLabel;
class QPushButton;
class QSpinBox;
class QToolButton;

class VideoControlDock : public QDockWidget
{
    Q_OBJECT
public:
    explicit VideoControlDock(PiControlPoller *poller,
                              QWidget *parent = nullptr);

private slots:
    void refreshFromPoller();
    void onApplyClicked();
    void onReconnectClicked();
    void onEditHostClicked();
    void onControlResult(int httpCode, QJsonObject payload);

private:
    void applyOptionsOnce();
    void updateGroupTitle();

    PiControlPoller *m_poller = nullptr;
    bool             m_optsApplied = false;

    QGroupBox   *m_box    = nullptr;
    QComboBox   *m_mode   = nullptr;
    QSpinBox    *m_w      = nullptr;
    QSpinBox    *m_h      = nullptr;
    QSpinBox    *m_fps    = nullptr;
    QSpinBox    *m_br     = nullptr;     // shown in kbps; sent as bps
    QCheckBox   *m_hflip  = nullptr;
    QCheckBox   *m_vflip  = nullptr;
    QPushButton *m_apply  = nullptr;
    QToolButton *m_reconnect = nullptr;
    QToolButton *m_editHost  = nullptr;
    QLabel      *m_status = nullptr;
    QLabel      *m_result = nullptr;
};
