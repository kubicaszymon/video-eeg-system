#pragma once

#include "appmodel.h"

#include <QElapsedTimer>
#include <QMainWindow>
#include <QVector>

class QStackedWidget;
class QTimer;
class WelcomeScreen;
class MonitorView;
class NewSessionDialog;
class StopConfirmDialog;
class FiltersPopover;
class SaveToast;
class PiControlClient;
class PiControlPoller;
class EegControlDock;
class VideoControlDock;
class LslEegReceiver;
class LslVideoReceiver;
class SessionRecorder;

// Owns the application state machine:
//   Welcome -> New session -> Preview -> Recording -> Stop confirm -> Welcome
// plus the filters popover and save toast.
// Hardware is fixed (BrainTech Perun32 + Raspberry Pi Camera v1) — no
// device-selection dialog.
class MainWindow : public QMainWindow
{
    Q_OBJECT
public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override;

protected:
    void resizeEvent(QResizeEvent *) override;
    bool eventFilter(QObject *obj, QEvent *event) override;

private:
    void goWelcome();
    void enterMonitor();              // push current state into MonitorView
    void openNewSession();
    void confirmNewSession(const Session &s);
    void startRecording();
    void requestStop();
    void saveRecording();
    void discardRecording();
    void addMarker(const QString &label = {});
    void removeMarker(int id);
    void onFiltersChanged(const Filters &f);

    QString nextFilename() const;
    bool dialogOpen() const;
    void repositionOverlays();

    // ---- state ----
    Screen  m_screen = Screen::Welcome;
    Session m_session;
    bool    m_hasSession = false;
    Filters m_filters;
    Devices m_devices;
    QVector<Marker> m_markers;
    int     m_nextMarkerId = 1;
    int     m_sessionNum = 5;
    qint64  m_elapsedMs = 0;
    QElapsedTimer m_recClock;

    // ---- widgets ----
    QStackedWidget    *m_stack = nullptr;
    WelcomeScreen     *m_welcome = nullptr;
    MonitorView       *m_monitor = nullptr;
    NewSessionDialog  *m_newDlg = nullptr;
    StopConfirmDialog *m_stopDlg = nullptr;
    FiltersPopover    *m_filtersPopover = nullptr;
    SaveToast         *m_toast = nullptr;
    QTimer            *m_recTimer = nullptr;
    QTimer            *m_clockTimer = nullptr;

    // ---- Pi remote control (HTTP+JSON to perun-control / picam-control) ----
    PiControlClient   *m_eegCtrlClient   = nullptr;
    PiControlPoller   *m_eegCtrlPoller   = nullptr;
    EegControlDock    *m_eegCtrlDock     = nullptr;
    PiControlClient   *m_videoCtrlClient = nullptr;
    PiControlPoller   *m_videoCtrlPoller = nullptr;
    VideoControlDock  *m_videoCtrlDock   = nullptr;

    // ---- LSL data streams ----
    LslEegReceiver    *m_eegReceiver   = nullptr;
    LslVideoReceiver  *m_videoReceiver = nullptr;

    // ---- recording (independent inlets; writes recordings/session_*/) ----
    SessionRecorder   *m_recorder = nullptr;
};
