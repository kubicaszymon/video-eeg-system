/*
 * ==========================================================================
 *  eegdatamodel.h — Circular Buffer Display Model for Real-Time EEG
 * ==========================================================================
 *
 *  PURPOSE:
 *    Provides the data backend for the EegGraph.qml waveform renderer.
 *    Implements a fixed-size circular buffer that continuously receives
 *    scaled EEG samples and exposes them through Qt's QAbstractTableModel
 *    interface for efficient, incremental QML updates.
 *
 *  DESIGN PATTERN:
 *    Bridge (QAbstractTableModel) — decouples the in-memory circular buffer
 *    from the QML rendering layer. The model/view separation allows QML to
 *    observe only the changed rows rather than re-reading the entire dataset.
 *
 *  CIRCULAR BUFFER ARCHITECTURE:
 *
 *    ┌──────────────────────────────────────────────────────────────┐
 *    │  Column 0: X-axis (time in seconds)                        │
 *    │  Column 1..N: Channel data (scaled pixel values)           │
 *    │                                                            │
 *    │  ┌─────────────────────────────────────────────────────┐   │
 *    │  │ ... old data ... │ GAP │ ← writePos → │ new data │   │
 *    │  └─────────────────────────────────────────────────────┘   │
 *    │                       ▲                                    │
 *    │              GAP_SIZE samples set to GAP_VALUE (1e9)       │
 *    │              so QML LineSeries breaks the line here        │
 *    └──────────────────────────────────────────────────────────────┘
 *
 *    The buffer wraps around: when m_currentIndex reaches m_maxSamples,
 *    it modulo-wraps to 0 and begins overwriting the oldest data.
 *    A "gap" of GAP_SIZE samples (set to GAP_VALUE = 1e9) is written
 *    AHEAD of the write cursor to create a visible break in the waveform,
 *    giving the classic "scrolling EEG" appearance.
 *
 *  BUFFER SIZING:
 *    m_maxSamples = samplingRate × timeWindowSeconds
 *    Example: 256 Hz × 10s = 2560 samples
 *
 *    When either samplingRate or timeWindowSeconds changes, the buffer is
 *    reallocated via recalculateMaxSamples() → initializeBuffer().
 *
 *  PERFORMANCE OPTIMIZATIONS:
 *    1. Incremental dataChanged signals — only the written row range is
 *       emitted, not a full model reset. This avoids re-rendering all
 *       2560+ data points on every 5-sample chunk arrival.
 *    2. Rate-limited UI updates — emitDataChanged() enforces a 16ms
 *       minimum interval (~60 FPS cap) to prevent overwhelming the QML
 *       rendering pipeline during high-frequency data arrival.
 *    3. Monotonic min/max cache — avoids full-buffer scans for Y-axis range.
 *
 *  DATA FLOW (input):
 *    EegBackend::onDataReceived()
 *      → EegDisplayScaler::transformChunk()   [μV → pixels]
 *        → EegDataModel::updateAllData()      [writes to circular buffer]
 *          → emitDataChanged()                [notifies QML]
 *            → EegGraph.qml re-renders
 *
 *  TABLE LAYOUT:
 *    Column 0:     X-axis — time in seconds (writeIndex / samplingRate)
 *    Column 1..N:  Y-axis — scaled pixel values per channel
 *    Rows:         One row per sample (0 to m_maxSamples-1)
 *
 * ==========================================================================
 */

#ifndef EEGDATAMODEL_H
#define EEGDATAMODEL_H

#include <QAbstractTableModel>
#include <QPointF>
#include <QVector>
#include <QTimer>
#include <QElapsedTimer>
#include <QtQmlIntegration>
#include <limits>

class EegDataModel : public QAbstractTableModel
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(double minValue READ minValue NOTIFY minMaxChanged)
    Q_PROPERTY(double maxValue READ maxValue NOTIFY minMaxChanged)
    Q_PROPERTY(int writePosition READ writePosition NOTIFY writePositionChanged)
    Q_PROPERTY(double samplingRate READ samplingRate WRITE setSamplingRate NOTIFY samplingRateChanged)
    Q_PROPERTY(double timeWindowSeconds READ timeWindowSeconds WRITE setTimeWindowSeconds NOTIFY timeWindowSecondsChanged)
    Q_PROPERTY(int maxSamples READ maxSamples NOTIFY maxSamplesChanged)

public:
    EegDataModel();

    // --- QAbstractTableModel interface ---

    /* Returns m_maxSamples (total rows in the circular buffer).
     * Returns 0 if the buffer has not been initialized yet. */
    int rowCount(const QModelIndex &parent = QModelIndex()) const override;

    /* Returns the number of data columns: 1 (X-axis) + N (channels).
     * Maps directly to m_data.size(). */
    int columnCount(const QModelIndex &parent = QModelIndex()) const override;

    /* Returns the double value at [row, column] for Qt::DisplayRole.
     * Row = sample index in the circular buffer.
     * Column 0 = time in seconds, Column 1..N = scaled pixel Y values. */
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;

    // --- Data entry ---

    /* Primary data entry point — called by EegBackend::onDataReceived().
     * Accepts pre-scaled data [channel][sample] from EegDisplayScaler.
     * Writes samples into the circular buffer at m_currentIndex (modulo),
     * inserts the GAP ahead of the cursor, and notifies QML via
     * rate-limited dataChanged signals. */
    Q_INVOKABLE void updateAllData(const QVector<QVector<double>>& incomingData);

    // --- Buffer configuration ---

    /* Returns the number of EEG channels currently in the buffer. */
    int channelCount() const;

    /* Explicitly sets the channel count. Triggers buffer reinitialization
     * if the count differs from the current configuration. */
    void setChannelCount(int newChannelCount);

    /* Returns the minimum scaled Y value seen so far (for Y-axis auto-range).
     * Returns 0.0 before any data has been received. */
    double minValue() const;

    /* Returns the maximum scaled Y value seen so far.
     * Returns 1000.0 before any data has been received. */
    double maxValue() const;

    /* Returns the current write cursor position within the circular buffer.
     * Used by EegGraph.qml to draw the sweep cursor indicator, and by
     * EegBackend to calculate marker X positions. */
    int writePosition() const;

    /* Returns the current sampling rate in Hz. Set by EegBackend when the
     * LSL stream reports its nominal_srate(). */
    double samplingRate() const;

    /* Updates the sampling rate and triggers buffer reallocation via
     * recalculateMaxSamples(). Rejects values <= 0. */
    void setSamplingRate(double newSamplingRate);

    /* Returns the display time window in seconds (e.g. 10.0 = 10s of data). */
    double timeWindowSeconds() const;

    /* Updates the time window and triggers buffer reallocation.
     * Changing from 10s to 5s halves the buffer size and clears all data. */
    void setTimeWindowSeconds(double newTimeWindowSeconds);

    /* Returns the total number of sample slots in the circular buffer.
     * Equals samplingRate × timeWindowSeconds (e.g. 256 × 10 = 2560). */
    int maxSamples() const;

signals:
    void channelCountChanged();

    /* Emitted when the Y-axis range (minValue/maxValue) changes.
     * QML can use this to auto-scale the chart axes. */
    void minMaxChanged();

    /* Emitted after each data write with the new cursor position.
     * QML uses this to animate the sweep cursor line. */
    void writePositionChanged();

    void samplingRateChanged();
    void timeWindowSecondsChanged();

    /* Emitted when m_maxSamples changes (due to samplingRate or
     * timeWindowSeconds change). Triggers QML chart axis reconfiguration. */
    void maxSamplesChanged();

private:
    /* Allocates (or reallocates) the m_data buffer for the given number
     * of channels. Wraps the operation in beginResetModel/endResetModel
     * to notify QML views of the structural change. Only runs when the
     * channel count or buffer size actually changes (guard check inside). */
    void initializeBuffer(int numChannels);

    /* Rate-limited dataChanged notification. Accumulates the union of all
     * changed-row ranges within a 16ms window, then emits a single
     * QAbstractItemModel::dataChanged covering the entire affected region.
     * This limits QML re-renders to ~60 FPS regardless of data arrival rate. */
    void emitDataChanged(int startRow, int endRow);

    /* Incrementally updates the min/max Y-value cache. Called for every
     * sample written. Skips GAP_VALUE sentinels. Emits minMaxChanged()
     * only when the range actually expands (monotonic — never shrinks). */
    void updateMinMaxCache(double value);

    /* Recomputes m_maxSamples from m_samplingRate × m_timeWindowSeconds.
     * If the result changes, triggers full buffer reinitialization.
     * Enforces a minimum of 100 samples to prevent degenerate buffers. */
    void recalculateMaxSamples();

    /* m_data[0] = X-axis (time); m_data[1..N] = channel Y values.
     * Each inner vector has exactly m_maxSamples elements. */
    QVector<QVector<double>> m_data;
    double m_channelSpacing = 100.0;
    int m_currentIndex = 0;         // Monotonically increasing write counter
    int m_totalSamples = 0;
    int m_writePosition = 0;        // Current write position (mod m_maxSamples)

    double m_samplingRate = 256.0;
    double m_timeWindowSeconds = 10.0;
    int m_maxSamples = 2560;        // = samplingRate × timeWindowSeconds

    /* GAP_SIZE samples ahead of the write cursor are set to GAP_VALUE.
     * QML's LineSeries treats these extreme values as line breaks,
     * producing the classic "sweeping cursor" EEG display effect. */
    static constexpr int GAP_SIZE = 50;
    // NaN causes QtGraphs LineSeries to produce a true line-break (no segment
    // is drawn to/from a NaN point).  The previous value of 1e9 was a finite
    // number so QtGraphs still drew a near-vertical spike from the last real
    // sample up to y=1e9 before clipping it — that was the visible spike bug.
    static constexpr double GAP_VALUE = std::numeric_limits<double>::quiet_NaN();
    static constexpr int DEFAULT_MAX_SAMPLES = 2560;

    double m_cachedMin = std::numeric_limits<double>::infinity();
    double m_cachedMax = -std::numeric_limits<double>::infinity();
    bool m_minMaxDirty = true;

    /* Rate limiter: accumulates changed-row ranges between UI flushes.
     * Ensures at most one dataChanged signal per 16ms (~60 FPS). */
    QElapsedTimer m_updateTimer;
    static constexpr int MIN_UPDATE_INTERVAL_MS = 16;
    bool m_pendingUpdate = false;
    int m_pendingStartRow = 0;
    int m_pendingEndRow = 0;

    bool m_bufferInitialized = false;
    int m_numChannels = 0;
};

#endif // EEGDATAMODEL_H
