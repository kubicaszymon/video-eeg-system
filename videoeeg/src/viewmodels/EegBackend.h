/*
 * ==========================================================================
 *  EegBackend.h — Central EEG Data Router & ViewModel
 * ==========================================================================
 *
 *  PURPOSE:
 *    The primary ViewModel for the EEG display window (EegWindow.qml).
 *    Acts as the central hub that receives raw EEG data from the hardware
 *    layer and routes it to three independent consumers:
 *      1. Display pipeline  — scales and feeds EegDataModel for visualization.
 *      2. Sync buffer       — feeds EegSyncManager for video-EEG alignment.
 *      3. Recording system  — feeds RecordingManager for persistent storage.
 *
 *  DESIGN PATTERNS:
 *    MVVM ViewModel (QML_ELEMENT) — bridges the C++ data layer with the QML UI.
 *    Facade — hides the complexity of AmplifierManager, EegDisplayScaler,
 *    MarkerManager, and EegSyncManager behind a single QML-facing interface.
 *    Composition — owns MarkerManager and EegDisplayScaler as sub-components.
 *
 *  COMPLETE DATA ROUTING (onDataReceived — the critical hot path):
 *
 *    AmplifierManager::dataReceived [raw μV, LSL timestamps]
 *              │
 *              ▼  (Qt::QueuedConnection — worker thread → main thread)
 *    EegBackend::onDataReceived()
 *              │
 *              ├──[1] DISPLAY ─────────────────────────────────────────────
 *              │   EegDisplayScaler::transformChunk()
 *              │     • Extracts selected channels via m_channelIndexCache
 *              │     • Transposes [sample][channel] → [channel][sample]
 *              │     • Applies μV → pixel scaling with Y-axis inversion
 *              │   EegDataModel::updateAllData()
 *              │     • Writes to circular buffer
 *              │     • Emits rate-limited dataChanged for QML
 *              │   updateMarkersAfterWrite()
 *              │     • Garbage-collects overwritten markers
 *              │
 *              ├──[2] SYNC BUFFER ─────────────────────────────────────────
 *              │   EegSyncManager::addEegSamples()
 *              │     • Stores raw data with LSL timestamps
 *              │     • Used later for video-EEG frame alignment
 *              │
 *              └──[3] RECORDING ───────────────────────────────────────────
 *                  RecordingManager::writeEegData()
 *                    • Batches data, flushes to CSV on worker thread
 *                    • No-op if recording is not active
 *
 *  CHANNEL INDEX CACHE:
 *    m_channels (QVariantList from QML) contains the user-selected channel
 *    indices as QVariants. Converting them to int on every data arrival would
 *    be wasteful (~50 calls/sec). m_channelIndexCache pre-converts to QVector<int>
 *    and is rebuilt only when the channel selection changes.
 *
 *  INITIALIZATION SEQUENCE (from QML):
 *    1. QML creates EegBackend and sets amplifierId, channels, spacing, etc.
 *    2. QML creates EegDataModel and calls registerDataModel(model).
 *    3. QML calls startStream() → connects to AmplifierManager.
 *    4. onSamplingRateDetected() configures EegDataModel buffer size.
 *    5. onStreamConnected() updates UI state.
 *    6. onDataReceived() begins the continuous data routing loop.
 *
 *  THREADING:
 *    All slots run on the main thread. The Qt::QueuedConnection in the
 *    constructor ensures that signals from AmplifierManager (which relays
 *    from the LSL worker thread) are safely marshalled to the main thread.
 *
 * ==========================================================================
 */

#ifndef EEGBACKEND_H
#define EEGBACKEND_H

#include <QObject>
#include <QVariantMap>
#include <QVector>
#include <QtQml/qqmlregistration.h>
#include "amplifiermodel.h"
#include "amplifiermanager.h"
#include "eegdatamodel.h"
#include "markermanager.h"
#include "eegdisplayscaler.h"
#include "eegsyncmanager.h"

class EegBackend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    // Channel configuration — set from AmplifierSetupWindow via main.qml
    Q_PROPERTY(QVariantList channels READ channels WRITE setChannels NOTIFY channelsChanged FINAL)
    Q_PROPERTY(QStringList channelNames READ channelNames NOTIFY channelsChanged FINAL)

    // Amplifier identification — set during device selection
    Q_PROPERTY(int amplifierIdx READ amplifierIdx WRITE setAmplifierIdx NOTIFY amplifierIdxChanged FINAL)
    Q_PROPERTY(QString amplifierId READ amplifierId WRITE setAmplifierId NOTIFY amplifierIdChanged FINAL)

    // Display configuration — adjustable at runtime from EEG control panel
    Q_PROPERTY(double spacing READ spacing WRITE setSpacing NOTIFY spacingChanged FINAL)
    Q_PROPERTY(double timeWindowSeconds READ timeWindowSeconds WRITE setTimeWindowSeconds NOTIFY timeWindowSecondsChanged FINAL)

    // Stream info — propagated from LSL stream metadata
    Q_PROPERTY(double samplingRate READ samplingRate NOTIFY samplingRateChanged FINAL)

    // Connection state — drives UI indicators (connecting spinner, connected badge)
    Q_PROPERTY(bool isConnecting READ isConnecting NOTIFY isConnectingChanged FINAL)
    Q_PROPERTY(bool isConnected READ isConnected NOTIFY isConnectedChanged FINAL)

    // Sub-components exposed to QML for direct property binding
    Q_PROPERTY(MarkerManager* markerManager READ markerManager CONSTANT FINAL)
    Q_PROPERTY(EegDisplayScaler* scaler READ scaler CONSTANT FINAL)

public:
    /* Constructor wires all signal/slot connections to AmplifierManager
     * with Qt::QueuedConnection for thread safety, and creates owned
     * sub-components (MarkerManager, EegDisplayScaler). */
    explicit EegBackend(QObject *parent = nullptr);
    ~EegBackend();

    // --- Initialization (called from QML in sequence) ---

    /* Called from QML after the EegDataModel is created in the QML context.
     * The model is not owned by this backend — it lives in the QML tree.
     * Must be called before startStream() for data to flow to the display. */
    Q_INVOKABLE void registerDataModel(EegDataModel* dataModel);

    /* Initiates the EEG streaming pipeline: launches Svarog Streamer,
     * creates the LSL reader thread, and begins data acquisition.
     * Sets isConnecting=true immediately; isConnected becomes true once
     * the LSL stream is resolved and the first data arrives. */
    Q_INVOKABLE void startStream();

    /* Tears down the streaming pipeline: stops LSL reader, kills Svarog
     * process. Resets connection state to disconnected. */
    Q_INVOKABLE void stopStream();

    /* Generates synthetic sinusoidal waveforms and pushes them to the
     * display model. Used for testing the UI rendering pipeline without
     * real hardware. Does not involve LSL or AmplifierManager. */
    Q_INVOKABLE void generateTestData();

    // --- Markers ---

    /* Places a visual marker at the current write cursor position and
     * simultaneously records it to the active recording session (if any).
     * @param type  Marker type key (e.g. "eyes_open", "seizure_start") */
    Q_INVOKABLE void addMarker(const QString& type);

    // --- Channel configuration ---

    /* Returns the list of selected channel indices as QVariants (for QML binding). */
    QVariantList channels() const;

    /* Sets the channel selection. Invalidates the cached index array so
     * it will be rebuilt on the next data arrival. */
    void setChannels(const QVariantList &newChannels);

    /* Resolves numeric channel indices to human-readable EEG labels
     * (e.g. "Fp1", "C3") by looking up the amplifier's metadata. */
    QStringList channelNames() const;

    // --- Amplifier identification ---

    /* Index of the selected amplifier in the discovery list (for QML ComboBox). */
    int amplifierIdx() const;
    void setAmplifierIdx(int newAmplifierIdx);

    /* Machine-readable amplifier ID string (e.g. "usb:002/005"), passed
     * to AmplifierManager::startStream() to identify which device to use. */
    QString amplifierId() const;
    void setAmplifierId(const QString &newAmplifierId);

    // --- Display configuration ---

    /* Vertical pixel spacing between channel baselines. Larger values
     * spread channels farther apart on screen. Default: 100 px. */
    double spacing() const;
    void setSpacing(double newSpacing);

    /* Display time window in seconds. Determines how many seconds of EEG
     * data are visible at once. Changing this reallocates the buffer. */
    double timeWindowSeconds() const;
    void setTimeWindowSeconds(double newTimeWindowSeconds);

    /* Sampling rate in Hz, as reported by the LSL stream. Read-only from QML. */
    double samplingRate() const;

    // --- Connection state (read-only from QML) ---

    /* True while waiting for LSL stream resolution (between startStream()
     * and onStreamConnected/error). Drives the "connecting..." spinner. */
    bool isConnecting() const { return m_isConnecting; }

    /* True after onStreamConnected(), false after stop or disconnect.
     * Drives the "connected" badge and enables the control panel. */
    bool isConnected() const { return m_isConnected; }

    // --- Owned sub-components (exposed to QML for direct binding) ---

    /* Provides access to the marker management system from QML. */
    MarkerManager* markerManager() const { return m_markerManager; }

    /* Provides access to the display scaler (sensitivity, DPI) from QML. */
    EegDisplayScaler* scaler() const { return m_scaler; }

public slots:
    /* Called when AmplifierManager reports a successful LSL connection.
     * Transitions state from "connecting" to "connected". */
    void onStreamConnected();

    /* Called when the LSL stream is lost or stopped.
     * Resets all connection state flags. */
    void onStreamDisconnected();

    /* Called once when the LSL stream reports its nominal sampling rate.
     * Propagates the rate to EegDataModel (buffer sizing) and
     * EegSyncManager (time calculations). */
    void onSamplingRateDetected(double samplingRate);

    /* THE HOT PATH — called ~50 times/sec with ~5 samples each.
     * Routes raw LSL data to three consumers:
     *   [1] Display — scale and write to circular buffer
     *   [2] Sync   — store raw data for video-EEG alignment
     *   [3] Record — batch and flush to CSV (if recording active) */
    void onDataReceived(const std::vector<std::vector<float>>& chunk,
                        const std::vector<double>& timestamps);

signals:
    void channelsChanged();
    void amplifierIdxChanged();
    void amplifierIdChanged();
    void spacingChanged();
    void samplingRateChanged();
    void timeWindowSecondsChanged();
    void isConnectingChanged();
    void isConnectedChanged();

private:
    /* Lazily rebuilds m_channelIndexCache from the QVariantList m_channels.
     * Only runs when the channel count has changed. */
    void updateChannelIndexCache();

    /* Garbage-collects markers that fell within the overwritten buffer range. */
    void updateMarkersAfterWrite(int prevWritePos, int newWritePos);

    AmplifierManager* m_amplifierManager = nullptr;

    /* m_channels: QVariantList of channel indices (set from QML).
     * m_channelIndexCache: pre-converted QVector<int> for hot-path use. */
    QVariantList m_channels;
    QVector<int> m_channelIndexCache;
    int m_amplifierIdx = 0;
    QString m_amplifierId;

    double m_spacing = 100.0;
    double m_timeWindowSeconds = 10.0;
    double m_samplingRate = 0.0;

    bool m_isConnecting = false;
    bool m_isConnected = false;

    EegDataModel* m_dataModel = nullptr;    // Not owned — lives in QML tree

    MarkerManager* m_markerManager = nullptr;       // Owned
    EegDisplayScaler* m_scaler = nullptr;           // Owned
};

#endif // EEGBACKEND_H
