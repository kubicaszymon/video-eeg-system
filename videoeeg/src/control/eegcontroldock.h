#pragma once

// EegControlDock — QDockWidget for remote-controlling the EEG Pi
// (perun-control.service, port 8080). Mirrors the EEG dock panel in
// pi_camera/pc_app/sync_prototype.py.
//
// Binds to a PiControlPoller; reads its cached snapshot in
// `refreshFromPoller()` (called on every `snapshotChanged()`). Sends control
// requests via `poller->sendControl()` / `poller->sendImpedance()`.

#include <QDockWidget>
#include <QJsonObject>     // moc needs the full type for the slots below
#include <QStringList>

class PiControlPoller;
class QComboBox;
class QGroupBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
class QToolButton;

class EegControlDock : public QDockWidget
{
    Q_OBJECT
public:
    explicit EegControlDock(PiControlPoller *poller, QWidget *parent = nullptr);

private slots:
    void refreshFromPoller();
    void onApplyClicked();
    void onImpedanceClicked();
    void onReconnectClicked();
    void onEditHostClicked();
    void onControlResult(int httpCode, QJsonObject payload);
    void onImpedanceResult(int httpCode, QJsonObject payload);

private:
    void applyOptionsOnce();
    void updateGroupTitle();

    PiControlPoller *m_poller = nullptr;
    bool             m_optsApplied = false;

    QGroupBox   *m_box       = nullptr;
    QComboBox   *m_mode      = nullptr;
    QComboBox   *m_rate      = nullptr;
    QLineEdit   *m_channels  = nullptr;
    QPushButton *m_apply     = nullptr;
    QSpinBox    *m_impDur    = nullptr;
    QPushButton *m_impBtn    = nullptr;
    QToolButton *m_reconnect = nullptr;
    QToolButton *m_editHost  = nullptr;
    QLabel      *m_status    = nullptr;
    QLabel      *m_result    = nullptr;
};
