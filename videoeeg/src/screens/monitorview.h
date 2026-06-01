#pragma once

#include "appmodel.h"

#include <QVector>
#include <QWidget>

class QLabel;
class QPushButton;
class QVBoxLayout;
class EegCanvas;
class VideoCanvas;
class VideoDock;

// ---- Sidebar (left rail: brand, session, devices, markers) ---------------
class Sidebar : public QWidget
{
    Q_OBJECT
public:
    explicit Sidebar(QWidget *parent = nullptr);

    void setRecording(bool on);
    void setSession(const Session &s, bool hasSession);
    void setDevices(const Devices &d);
    void setFilters(const Filters &f);
    void setMarkers(const QVector<Marker> &m);

signals:
    void addMarkerRequested();
    void removeMarkerRequested(int id);

private:
    void rebuildSession();
    void rebuildMarkers();

    bool m_recording = false;
    bool m_hasSession = false;
    Session m_session;
    Devices m_devices;
    Filters m_filters;
    QVector<Marker> m_markers;

    QVBoxLayout *m_sessionBox = nullptr;
    QLabel  *m_ampVal = nullptr;
    QLabel  *m_camVal = nullptr;
    QLabel  *m_stoVal = nullptr;
    QLabel  *m_filVal = nullptr;
    QWidget *m_markerSection = nullptr;
    QVBoxLayout *m_markerList = nullptr;
    QLabel  *m_markerCount = nullptr;
};

// ---- Top bar -------------------------------------------------------------
class Topbar : public QWidget
{
    Q_OBJECT
public:
    explicit Topbar(QWidget *parent = nullptr);

    void setRecording(bool on);
    void setSession(const Session &s, bool hasSession);

signals:
    void startRequested();
    void stopRequested();
    void newSessionRequested();
    void filtersRequested();

private:
    void refresh();

    bool m_recording = false;
    bool m_hasSession = false;
    Session m_session;

    QLabel *m_kicker = nullptr;
    QLabel *m_title = nullptr;
    QWidget *m_recPill = nullptr;
    QPushButton *m_newSession = nullptr;
    QPushButton *m_primary = nullptr;   // Start
    QPushButton *m_danger = nullptr;    // Stop
};

// ---- Metric bar ----------------------------------------------------------
class MetricBar : public QWidget
{
    Q_OBJECT
public:
    explicit MetricBar(QWidget *parent = nullptr);

    void setRecording(bool on);
    void setElapsed(qint64 ms);
    void setClock(const QString &c);

private:
    bool m_recording = false;
    qint64 m_elapsed = 0;
    QLabel *m_elapsedV = nullptr;
    QLabel *m_samplesV = nullptr;
    QLabel *m_diskV = nullptr;
    QLabel *m_clockV = nullptr;
};

// ---- Monitor view (sidebar + topbar + metrics + canvases) ----------------
class MonitorView : public QWidget
{
    Q_OBJECT
public:
    explicit MonitorView(QWidget *parent = nullptr);

    void setScreen(Screen s);
    void setSession(const Session &s, bool hasSession);
    void setDevices(const Devices &d);
    void setFilters(const Filters &f);
    void setMarkers(const QVector<Marker> &m);
    void setElapsed(qint64 ms);
    void setClock(const QString &c);

    // Access to the canvases so MainWindow can attach LSL receivers.
    // Video is now embedded inside a floating VideoDock that overlays
    // the EEG area; videoCanvas() returns the inner VideoCanvas the dock
    // owns, so the MainWindow wiring (setReceiver) is unchanged.
    EegCanvas   *eegCanvas()   const { return m_eeg; }
    VideoCanvas *videoCanvas() const { return m_video; }
    VideoDock   *videoDock()   const { return m_videoDock; }

signals:
    void startRequested();
    void stopRequested();
    void newSessionRequested();
    void filtersRequested();
    void addMarkerRequested();
    void removeMarkerRequested(int id);

protected:
    void resizeEvent(QResizeEvent *) override;

private:
    void layoutHints();

    Sidebar     *m_sidebar = nullptr;
    Topbar      *m_topbar = nullptr;
    MetricBar   *m_metrics = nullptr;
    EegCanvas   *m_eeg = nullptr;
    VideoCanvas *m_video = nullptr;    // owned by VideoDock now
    VideoDock   *m_videoDock = nullptr;
    QWidget     *m_hints = nullptr;
    Screen       m_screen = Screen::Preview;
};
