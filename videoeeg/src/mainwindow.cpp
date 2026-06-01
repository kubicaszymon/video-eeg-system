#include "mainwindow.h"
#include "canvases.h"
#include "eegcontroldock.h"
#include "format.h"
#include "lsleegreceiver.h"
#include "lslvideoreceiver.h"
#include "monitorview.h"
#include "overlays.h"
#include "picontrolclient.h"
#include "picontrolpoller.h"
#include "sessionrecorder.h"
#include "videocontroldock.h"
#include "welcomescreen.h"

#include <QApplication>
#include <QDir>
#include <QEvent>
#include <QKeyEvent>
#include <QResizeEvent>
#include <QSettings>
#include <QStackedWidget>
#include <QTime>
#include <QTimer>

#include <algorithm>

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent)
{
    setWindowTitle(QStringLiteral("NeuroSync VEEG — Research Prototype"));

    m_stack = new QStackedWidget;
    setCentralWidget(m_stack);

    m_welcome = new WelcomeScreen;
    m_monitor = new MonitorView;
    m_stack->addWidget(m_welcome);
    m_stack->addWidget(m_monitor);

    m_newDlg = new NewSessionDialog(this);
    m_stopDlg = new StopConfirmDialog(this);
    m_filtersPopover = new FiltersPopover(this);
    m_toast = new SaveToast(this);

    // ---- wiring ----
    connect(m_welcome, &WelcomeScreen::startRequested,
            this, &MainWindow::openNewSession);

    connect(m_monitor, &MonitorView::startRequested,
            this, &MainWindow::startRecording);
    connect(m_monitor, &MonitorView::stopRequested,
            this, &MainWindow::requestStop);
    connect(m_monitor, &MonitorView::newSessionRequested,
            this, &MainWindow::openNewSession);
    connect(m_monitor, &MonitorView::filtersRequested,
            this, [this] { m_filtersPopover->toggle(); });
    connect(m_monitor, &MonitorView::addMarkerRequested,
            this, [this] { addMarker(); });
    connect(m_monitor, &MonitorView::removeMarkerRequested,
            this, &MainWindow::removeMarker);

    connect(m_newDlg, &NewSessionDialog::confirmed,
            this, &MainWindow::confirmNewSession);
    connect(m_stopDlg, &StopConfirmDialog::saveRequested,
            this, &MainWindow::saveRecording);
    connect(m_stopDlg, &StopConfirmDialog::discardRequested,
            this, &MainWindow::discardRecording);
    connect(m_filtersPopover, &FiltersPopover::filtersChanged,
            this, &MainWindow::onFiltersChanged);

    // ---- timers ----
    // Recording-metrics ticker. The visible metrics are hh:mm:ss + a samples
    // count + an MB estimate -- all human-readable, no use updating faster
    // than once a second. (Was 100 ms originally; that caused 10x the QLabel
    // setText work, which felt like a lag spike when recording started.)
    m_recTimer = new QTimer(this);
    m_recTimer->setInterval(1000);
    m_recTimer->setTimerType(Qt::CoarseTimer);
    connect(m_recTimer, &QTimer::timeout, this, [this] {
        m_elapsedMs = m_recClock.elapsed();
        m_monitor->setElapsed(m_elapsedMs);
    });

    m_clockTimer = new QTimer(this);
    m_clockTimer->setInterval(1000);
    connect(m_clockTimer, &QTimer::timeout, this, [this] {
        m_monitor->setClock(fmt::clock(QTime::currentTime()));
    });
    m_clockTimer->start();

    m_welcome->setDevices(m_devices);
    m_filtersPopover->setFilters(m_filters);

    // ----------------------------------------------------------------------
    // Pi remote control docks. One client+poller per Pi, then a dock widget
    // each. Hosts are the canonical names from CLAUDE.md; the daemons listen
    // on 8080 (EEG) and 8081 (video). Auth token left blank: the API is open
    // on the closed research LAN (set a token in the .service file + here
    // when deploying outside the lab).
    //
    // Both docks dock to the right by default; QDockWidget lets the user
    // detach / re-dock / hide them at runtime.
    // ----------------------------------------------------------------------
    // Host/port for each Pi: a user override saved via the docks' "…" edit
    // dialog wins; otherwise we fall back to the canonical names from
    // CLAUDE.md (camera-pi.local:8080 / video-pi.local:8081).
    QSettings cfg;
    cfg.beginGroup(QStringLiteral("eegControl"));
    const QString eegHost = cfg.value(QStringLiteral("host"),
        QStringLiteral("camera-pi.local")).toString();
    const quint16 eegPort = static_cast<quint16>(cfg.value(
        QStringLiteral("port"), 8080).toUInt());
    cfg.endGroup();
    cfg.beginGroup(QStringLiteral("videoControl"));
    const QString vidHost = cfg.value(QStringLiteral("host"),
        QStringLiteral("video-pi.local")).toString();
    const quint16 vidPort = static_cast<quint16>(cfg.value(
        QStringLiteral("port"), 8081).toUInt());
    cfg.endGroup();

    m_eegCtrlClient = new PiControlClient(eegHost, eegPort, QString{}, this);
    m_eegCtrlPoller = new PiControlPoller(m_eegCtrlClient, this);
    m_eegCtrlDock   = new EegControlDock(m_eegCtrlPoller, this);
    addDockWidget(Qt::RightDockWidgetArea, m_eegCtrlDock);

    m_videoCtrlClient = new PiControlClient(vidHost, vidPort, QString{}, this);
    m_videoCtrlPoller = new PiControlPoller(m_videoCtrlClient, this);
    m_videoCtrlDock   = new VideoControlDock(m_videoCtrlPoller, this);
    addDockWidget(Qt::RightDockWidgetArea, m_videoCtrlDock);

    // Defer poller start until the event loop is actually running. Without
    // this, both pollers start while MainWindow is still being constructed,
    // and on Windows the first burst of QNetworkAccessManager activity can
    // briefly stall the message pump ("not responding") before the window
    // even shows. singleShot(0,...) hops it to the next event-loop tick.
    QTimer::singleShot(0, this, [this]() {
        m_eegCtrlPoller->start(1000);
        m_videoCtrlPoller->start(1000);
    });

    // ----------------------------------------------------------------------
    // LSL data: background QThread receiver pulling `Perun32` (the EEG
    // stream the Pi daemon publishes). On chunkReceived the EegCanvas
    // re-paints with real samples; if the Pi is offline the canvas falls
    // back to its synthetic-sine fallback automatically.
    // ----------------------------------------------------------------------
    m_eegReceiver = new LslEegReceiver(QStringLiteral("Perun32"),
                                       /*bufferSeconds=*/10.0, this);
    m_monitor->eegCanvas()->setReceiver(m_eegReceiver);
    m_eegReceiver->start();

    // Video stream from the camera Pi (H.264 over LSL). Decoder lives in
    // the receiver QThread; frameReady() is queued onto the GUI thread to
    // trigger VideoCanvas repaint.
    m_videoReceiver = new LslVideoReceiver(
        QStringLiteral("Perun32_Video"), this);
    m_monitor->videoCanvas()->setReceiver(m_videoReceiver);
    m_videoReceiver->start();

    // ----------------------------------------------------------------------
    // Recorder. Independent of the display receivers above: it opens its OWN
    // LSL inlets so a laggy UI can never corrupt a recording (LSL allows many
    // consumers). Writes recordings/session_*/ in the same format as the
    // Python tool — see SessionRecorder / VIDEO_EEG_APP_SPEC.md. Root is
    // <cwd>/recordings (the app is launched from the veeg_app dir).
    // Not a QObject, so it is owned by a plain pointer and deleted in the
    // destructor path via stop(); we keep one instance and reuse it.
    // ----------------------------------------------------------------------
    const QString recRoot = QDir::current().filePath(QStringLiteral("recordings"));
    m_recorder = new SessionRecorder(QStringLiteral("Perun32"),
                                     QStringLiteral("Perun32_Video"),
                                     recRoot);

    qApp->installEventFilter(this);
    goWelcome();
}

MainWindow::~MainWindow()
{
    // SessionRecorder is not a QObject, so it isn't parented/auto-deleted.
    // Its destructor stops + joins any in-flight recording.
    delete m_recorder;
}

QString MainWindow::nextFilename() const
{
    return QStringLiteral("session_%1.edf")
        .arg(m_sessionNum, 3, 10, QLatin1Char('0'));
}

bool MainWindow::dialogOpen() const
{
    return m_newDlg->isVisible() || m_stopDlg->isVisible();
}

void MainWindow::goWelcome()
{
    m_screen = Screen::Welcome;
    m_recTimer->stop();
    m_filtersPopover->hide();
    m_welcome->setDevices(m_devices);
    m_stack->setCurrentWidget(m_welcome);
}

void MainWindow::enterMonitor()
{
    m_monitor->setScreen(m_screen);
    m_monitor->setSession(m_session, m_hasSession);
    m_monitor->setDevices(m_devices);
    m_monitor->setFilters(m_filters);
    m_monitor->setMarkers(m_markers);
    m_monitor->setElapsed(m_elapsedMs);
    m_monitor->setClock(fmt::clock(QTime::currentTime()));
    m_stack->setCurrentWidget(m_monitor);
}

void MainWindow::openNewSession()
{
    Session prefill;
    prefill.subject = m_hasSession && !m_session.subject.isEmpty()
                          ? m_session.subject
                          : QStringLiteral("S-024");
    prefill.op = m_hasSession && !m_session.op.isEmpty()
                     ? m_session.op
                     : QStringLiteral("m.kowalski");
    prefill.filename = nextFilename();
    prefill.notes.clear();
    m_newDlg->openWith(prefill);
}

void MainWindow::confirmNewSession(const Session &s)
{
    m_session = s;
    m_hasSession = true;
    m_markers.clear();
    m_nextMarkerId = 1;
    m_elapsedMs = 0;
    m_screen = Screen::Preview;
    enterMonitor();
}

void MainWindow::startRecording()
{
    if (!m_hasSession)
        return;
    m_elapsedMs = 0;
    m_session.startedAtClock = fmt::clock(QTime::currentTime());

    // Spin up the independent-inlet recorder. It resolves its own LSL streams
    // in background threads, so this returns immediately even if a Pi is slow.
    const QString sessionDir = m_recorder
        ? m_recorder->start(m_session.subject, m_session.op, m_session.notes)
        : QString{};
    if (sessionDir.isEmpty() && m_recorder)
        m_toast->show(QStringLiteral("Recorder error: %1")
                          .arg(m_recorder->lastError()));

    m_screen = Screen::Recording;
    m_recClock.restart();
    m_recTimer->start();
    enterMonitor();
}

void MainWindow::requestStop()
{
    m_stopDlg->openWith(m_elapsedMs, m_markers.size(), m_session);
}

void MainWindow::saveRecording()
{
    m_recTimer->stop();

    // Stop the workers (flush + join) and keep the files on disk.
    QString savedName = m_session.filename;
    if (m_recorder) {
        const QString sessionDir = m_recorder->dir();
        const SessionRecorder::Stats st = m_recorder->stats();
        m_recorder->stop();
        if (!sessionDir.isEmpty()) {
            savedName = QDir(sessionDir).dirName();
            qInfo() << "Saved session" << sessionDir
                    << "eeg=" << st.eegSamples << "samp  video="
                    << st.videoAUs << "AU";
        }
    }

    const QString dur = fmt::elapsed(m_elapsedMs);
    ++m_sessionNum;
    m_session = Session{};
    m_hasSession = false;
    m_markers.clear();
    m_elapsedMs = 0;
    goWelcome();
    m_toast->show(QStringLiteral("Saved %1 · %2").arg(savedName, dur));
}

void MainWindow::discardRecording()
{
    m_recTimer->stop();

    // Stop the workers and delete the session directory entirely.
    if (m_recorder) {
        const QString sessionDir = m_recorder->dir();
        m_recorder->stop();
        if (!sessionDir.isEmpty())
            QDir(sessionDir).removeRecursively();
    }

    m_session = Session{};
    m_hasSession = false;
    m_markers.clear();
    m_elapsedMs = 0;
    goWelcome();
    m_toast->show(QStringLiteral("Discarded recording (not saved)"));
}

void MainWindow::addMarker(const QString &label)
{
    Marker m;
    m.id = m_nextMarkerId++;
    m.elapsedMs = m_elapsedMs;
    m.label = label.isEmpty()
                  ? QStringLiteral("Marker %1").arg(m_nextMarkerId)
                  : label;
    m_markers.push_back(m);
    m_monitor->setMarkers(m_markers);
}

void MainWindow::removeMarker(int id)
{
    m_markers.erase(std::remove_if(m_markers.begin(), m_markers.end(),
                                   [id](const Marker &m) { return m.id == id; }),
                    m_markers.end());
    m_monitor->setMarkers(m_markers);
}

void MainWindow::onFiltersChanged(const Filters &f)
{
    m_filters = f;
    if (m_screen != Screen::Welcome)
        m_monitor->setFilters(m_filters);
}

void MainWindow::resizeEvent(QResizeEvent *e)
{
    QMainWindow::resizeEvent(e);
    repositionOverlays();
}

void MainWindow::repositionOverlays()
{
    for (ModalOverlay *o : {static_cast<ModalOverlay *>(m_newDlg),
                            static_cast<ModalOverlay *>(m_stopDlg)}) {
        if (o->isVisible())
            o->reposition();
    }
    if (m_filtersPopover->isVisible())
        m_filtersPopover->reposition();
    if (m_toast->isVisible())
        m_toast->reposition();
}

bool MainWindow::eventFilter(QObject *obj, QEvent *event)
{
    if (event->type() != QEvent::KeyPress)
        return QMainWindow::eventFilter(obj, event);

    auto *ke = static_cast<QKeyEvent *>(event);

    // never steal keys while typing or while a modal dialog is up
    QWidget *fw = qApp->focusWidget();
    if (fw && fw->inherits("QLineEdit"))
        return QMainWindow::eventFilter(obj, event);
    if (dialogOpen())
        return QMainWindow::eventFilter(obj, event);

    const int key = ke->key();
    if (key == Qt::Key_N && m_screen == Screen::Welcome) {
        openNewSession();
        return true;
    }
    if (key == Qt::Key_Space && m_screen == Screen::Preview) {
        startRecording();
        return true;
    }
    if (key == Qt::Key_Space && m_screen == Screen::Recording) {
        requestStop();
        return true;
    }
    if (key == Qt::Key_M && m_screen == Screen::Recording) {
        addMarker();
        return true;
    }
    if (key == Qt::Key_F && m_screen != Screen::Welcome) {
        m_filtersPopover->toggle();
        return true;
    }
    if (key == Qt::Key_Escape) {
        m_filtersPopover->hide();
        return true;
    }
    return QMainWindow::eventFilter(obj, event);
}
