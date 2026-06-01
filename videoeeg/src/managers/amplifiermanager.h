/*
 * ==========================================================================
 *  amplifiermanager.h — EEG Amplifier Orchestration Singleton
 * ==========================================================================
 *
 *  PURPOSE:
 *    Central coordinator for EEG hardware interaction. Manages the full
 *    lifecycle of amplifier discovery and data streaming:
 *      1. Device discovery — launches Svarog Streamer with "-l" flag to
 *         enumerate connected EEG amplifiers via USB.
 *      2. Stream control — launches Svarog Streamer with "-a <id>" to begin
 *         data acquisition, then starts an LSLStreamReader on a worker thread
 *         to pull the resulting LSL stream.
 *      3. Data relay — re-emits raw EEG chunks from LSLStreamReader to all
 *         downstream consumers (EegBackend, RecordingManager, EegSyncManager).
 *
 *  DESIGN PATTERNS:
 *    Singleton (Meyer's) — single instance accessed via instance().
 *    Mediator — decouples the LSL transport layer (LSLStreamReader) from
 *    the presentation layer (EegBackend) and persistence layer (RecordingManager).
 *
 *  EXTERNAL DEPENDENCY:
 *    Svarog Streamer (svarog_streamer.exe) — BrainTech Perun32 driver that
 *    bridges USB-connected EEG amplifiers to LSL network streams.
 *    Reference: https://braintech.pl/pliki/svarog/manuals/Perun32_instrukcja_obslugi.pdf
 *
 *  DATA FLOW:
 *    ┌──────────────┐  USB   ┌───────────────────┐  LSL    ┌────────────────┐
 *    │ EEG Hardware  │──────▸│ Svarog Streamer    │───────▸│ LSLStreamReader │
 *    └──────────────┘        │ (QProcess)         │        │ (QThread)       │
 *                            └───────────────────┘        └───────┬────────┘
 *                                                                  │
 *                                                    dataReceived signal
 *                                                                  │
 *                                                         ┌───────▼────────┐
 *                                                         │AmplifierManager│
 *                                                         │  (re-emits)    │
 *                                                         └───┬───┬───┬───┘
 *                                                             │   │   │
 *                                          ┌──────────────────┘   │   └──────────────────┐
 *                                          ▼                      ▼                      ▼
 *                                    EegBackend           EegSyncManager         RecordingManager
 *                                   (display)            (time alignment)        (file storage)
 *
 *  THREADING:
 *    Main thread: AmplifierManager itself, QProcess management, signal relay.
 *    Worker thread: m_lslThread hosts m_lslReader (LSLStreamReader).
 *    All cross-thread communication uses Qt::QueuedConnection (implicit for
 *    moveToThread objects).
 *
 *  STARTUP SEQUENCE (startStream):
 *    1. Launch svarog_streamer -a <amplifierId>  (QProcess)
 *    2. Wait for process start confirmation
 *    3. Create QThread + LSLStreamReader (if not already alive)
 *    4. Wire all signal/slot connections
 *    5. After 1s delay → emit startLslReading()
 *       WHY 1s DELAY: Svarog Streamer needs time to initialize its LSL outlet
 *       before LSLStreamReader can resolve it. Without this delay, resolve_stream()
 *       would timeout because no outlet exists yet.
 *
 *  SHUTDOWN SEQUENCE (stopStream):
 *    1. Signal LSLStreamReader to stop → sets m_isRunning = false
 *    2. Wait 100ms for the reader loop to exit gracefully
 *    3. Quit QThread event loop → wait up to 3s → terminate if stuck
 *    4. Terminate Svarog Streamer process → kill if unresponsive
 *
 * ==========================================================================
 */

#ifndef AMPLIFIERMANAGER_H
#define AMPLIFIERMANAGER_H

#include <QByteArray>
#include <QList>
#include <QString>
#include <QProcess>
#include <QThread>

#include "lslstreamreader.h"
#include "amplifiermodel.h"

class AmplifierManager : public QObject
{
    Q_OBJECT

public:
    /* Returns the singleton instance (Meyer's pattern — thread-safe,
     * lazy-initialized on first call). */
    static AmplifierManager* instance();

    AmplifierManager(const AmplifierManager&) = delete;
    AmplifierManager& operator=(const AmplifierManager&) = delete;

    /* Synchronous device discovery — launches `svarog_streamer -l` and blocks
     * up to PROCESS_TIMEOUT_MS for the result. Parses stdout into Amplifier structs.
     * Returns the discovered amplifiers and caches them in m_amplifiers.
     * Suitable for initial setup; avoid on the main thread during streaming. */
    QList<Amplifier> refreshAmplifiersList();

    /* Asynchronous device discovery — launches `svarog_streamer -l` in the
     * background and emits amplifiersListRefreshed(list) when done.
     * Preferred over the blocking variant for UI-triggered scans. */
    void refreshAmplifiersListAsync();

    /* Looks up a cached amplifier by its machine-readable id (e.g. "usb:002/005").
     * Returns nullptr if not found. The pointer is valid until the next refresh. */
    Amplifier* getAmplifierById(const QString& id);

    /* Full startup sequence: launches Svarog Streamer for the given amplifier,
     * creates a worker thread + LSLStreamReader, and begins data acquisition
     * after a STREAM_STARTUP_DELAY_MS delay. See header docs for full sequence. */
    void startStream(const QString& amplifierId);

    /* Full shutdown sequence: stops the LSL reader loop, tears down the worker
     * thread, and terminates the Svarog Streamer process. See header docs. */
    void stopStream();

    /* Parses the structured text output of `svarog_streamer -l` into
     * Amplifier structs. Uses a state-machine parser to handle multi-line
     * sections for channel names and sampling rates.
     * Public for testability — normally called internally by refresh methods. */
    QList<Amplifier> parseRawOutputToAmplifiers(const QByteArray& output);

    /* Getter/setter for the filesystem path to svarog_streamer.exe. */
    QString svarogPath() const;
    void setSvarogPath(const QString& newSvarogPath);

signals:
    /* Internal control signals — connected to LSLStreamReader slots via
     * Qt::QueuedConnection to cross the thread boundary. These are emitted
     * by startStream()/stopStream() to command the worker thread. */
    void startLslReading();
    void stopLslReading();

    /* Emitted when the acquisition state changes (connected/disconnected). */
    void acquisitionStatusChanged();

    /* Emitted by the async scan when parsing completes. Carries the full
     * list of discovered amplifiers for the UI to display. */
    void amplifiersListRefreshed(const QList<Amplifier>& amplifiers);

    /* Re-emitted from LSLStreamReader — these are the primary signals that
     * EegBackend, EegSyncManager, and RecordingManager connect to.
     * They carry data from the worker thread to the main thread. */
    void dataReceived(const std::vector<std::vector<float>>& chunk,
                      const std::vector<double>& timestamps);
    void samplingRateDetected(double samplingRate);
    void streamConnected();
    void streamDisconnected();

public slots:
    /* Relay slot: receives raw EEG data from LSLStreamReader (worker thread)
     * and re-emits it as dataReceived() for main-thread consumers.
     * This indirection is necessary because LSLStreamReader is on a different
     * thread and the signal must be re-emitted from a main-thread object. */
    void onProcessData(const std::vector<std::vector<float>>& chunk,
                       const std::vector<double>& timestamps);

    /* Relay slot: re-emits the sampling rate from LSLStreamReader. */
    void onSamplingRateDetected(double samplingRate);

private slots:
    /* Called when the async scan process (svarog_streamer -l) finishes.
     * Parses the output and emits amplifiersListRefreshed(). */
    void onScanProcessFinished(int exitCode, QProcess::ExitStatus exitStatus);

private:
    /* Private constructor/destructor enforce the singleton pattern. */
    AmplifierManager(QObject* parent = nullptr);
    ~AmplifierManager();

    QProcess* m_scanProcess = nullptr;      // `svarog_streamer -l` (device enumeration)
    QProcess* m_streamProcess = nullptr;    // `svarog_streamer -a <id>` (data streaming)

    // TODO: Make configurable via settings/options
    QString m_svarogPath{"C:\\Program Files (x86)\\Svarog Streamer\\svarog_streamer\\svarog_streamer.exe"};

    QThread* m_lslThread = nullptr;                 // Hosts m_lslReader worker
    std::unique_ptr<LSLStreamReader> m_lslReader;   // The actual LSL data puller

    /* Cache of discovered amplifiers — populated by refresh methods,
     * queried by getAmplifierById() and EegBackend::channelNames(). */
    QList<Amplifier> m_amplifiers{};

    static constexpr int PROCESS_TIMEOUT_MS = 3000;       // Max wait for svarog_streamer startup
    static constexpr int STREAM_STARTUP_DELAY_MS = 1000;  // Delay before LSL resolution attempt
};

#endif // AMPLIFIERMANAGER_H
