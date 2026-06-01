/*
 * ==========================================================================
 *  eegdatamodel.cpp — Circular Buffer Display Model Implementation
 * ==========================================================================
 *  See eegdatamodel.h for architecture overview, buffer layout, and
 *  performance optimization rationale.
 * ==========================================================================
 */

#include "eegdatamodel.h"
#include <QtCore/qnumeric.h>
#include <algorithm>

EegDataModel::EegDataModel()
{
    qInfo() << "EEGDATAMODEL CREATED " << this;
    /* Start the elapsed timer immediately so that the first emitDataChanged()
     * call has a valid reference point for rate-limiting. */
    m_updateTimer.start();
}

// ============================================================================
// QAbstractTableModel Interface
// ============================================================================

int EegDataModel::rowCount(const QModelIndex &parent) const
{
    /* Returns 0 before first data arrival (buffer not yet allocated),
     * then returns the fixed buffer size for the remainder of the session. */
    Q_UNUSED(parent);
    if (!m_bufferInitialized || m_data.empty())
    {
        return 0;
    }
    return m_maxSamples;
}

int EegDataModel::columnCount(const QModelIndex &parent) const
{
    /* Column count = 1 (X-axis time column) + N (one per EEG channel).
     * Returns 0 before the buffer is initialized. */
    Q_UNUSED(parent);
    return m_data.size();
}

QVariant EegDataModel::data(const QModelIndex &index, int role) const
{
    /* Called by QML's LineSeries/XYSeries to fetch individual data points.
     * Only Qt::DisplayRole is supported — returns the raw double value.
     * Returns an invalid QVariant for out-of-bounds or non-display requests. */
    if (!index.isValid()) return QVariant();

    if (role == Qt::DisplayRole)
    {
        int col = index.column();
        int row = index.row();

        if (col < m_data.size() && row < m_data[col].size())
        {
            return m_data[col][row];
        }
    }
    return QVariant();
}

// ============================================================================
// Buffer Management
// ============================================================================

void EegDataModel::initializeBuffer(int numChannels)
{
    if (m_bufferInitialized && m_numChannels == numChannels && !m_data.empty() && m_data[0].size() == m_maxSamples)
    {
        return;
    }

    beginResetModel();

    /* Allocate columns: [0]=X-axis + [1..N]=channels.
     * All vectors are pre-sized to m_maxSamples for zero-reallocation writes. */
    m_data.clear();
    m_data.resize(numChannels + 1);

    for (int col = 0; col <= numChannels; ++col)
    {
        m_data[col].resize(m_maxSamples);
    }

    /* Initialize X-axis with time values; fill channel columns with GAP_VALUE
     * so the initial waveform appears blank (no spurious lines). */
    for (int i = 0; i < m_maxSamples; ++i)
    {
        m_data[0][i] = static_cast<double>(i) / m_samplingRate;
        for (int ch = 0; ch < numChannels; ++ch)
        {
            m_data[ch + 1][i] = GAP_VALUE;
        }
    }

    m_currentIndex = 0;
    m_writePosition = 0;
    m_numChannels = numChannels;
    m_bufferInitialized = true;
    m_minMaxDirty = true;

    endResetModel();

    qInfo() << "EegDataModel buffer initialized for" << numChannels << "channels,"
            << m_maxSamples << "samples," << m_samplingRate << "Hz,"
            << m_timeWindowSeconds << "seconds window";
}

// ============================================================================
// Rate-Limited UI Notification
// ============================================================================

void EegDataModel::emitDataChanged(int startRow, int endRow)
{
    /*
     * At 256 Hz with 20ms LSL poll intervals, updateAllData() is called ~50
     * times per second with ~5 samples each. Without rate limiting, this would
     * trigger 50 dataChanged signals per second. The QML renderer cannot keep
     * up, causing frame drops and input lag.
     *
     * Solution: accumulate changed-row ranges and flush at most once per 16ms.
     * Pending ranges are merged (union of min/max) so no changes are lost.
     */
    qint64 elapsed = m_updateTimer.elapsed();

    if (elapsed < MIN_UPDATE_INTERVAL_MS)
    {
        if (m_pendingUpdate)
        {
            m_pendingStartRow = std::min(m_pendingStartRow, startRow);
            m_pendingEndRow = std::max(m_pendingEndRow, endRow);
        }
        else
        {
            m_pendingUpdate = true;
            m_pendingStartRow = startRow;
            m_pendingEndRow = endRow;
        }
        return;
    }

    if (m_pendingUpdate)
    {
        startRow = std::min(m_pendingStartRow, startRow);
        endRow = std::max(m_pendingEndRow, endRow);
        m_pendingUpdate = false;
    }

    QModelIndex topLeft = index(startRow, 0);
    QModelIndex bottomRight = index(endRow, m_data.size() - 1);
    emit QAbstractItemModel::dataChanged(topLeft, bottomRight);

    m_updateTimer.restart();
}

// ============================================================================
// Min/Max Tracking
// ============================================================================

void EegDataModel::updateMinMaxCache(double value)
{
    /* Skip GAP_VALUE sentinels (NaN) — they would corrupt the Y-axis range.
     * NaN comparisons always return false, so we must use qIsNaN() explicitly. */
    if (qIsNaN(value)) return;

    bool changed = false;
    if (value < m_cachedMin)
    {
        m_cachedMin = value;
        changed = true;
    }
    if (value > m_cachedMax)
    {
        m_cachedMax = value;
        changed = true;
    }

    if (changed)
    {
        emit minMaxChanged();
    }
}

// ============================================================================
// Primary Data Entry
// ============================================================================

void EegDataModel::updateAllData(const QVector<QVector<double>>& incomingData)
{
    if (incomingData.isEmpty() || incomingData[0].isEmpty())
    {
        return;
    }

    int newSamples = incomingData[0].size();
    int numChannels = incomingData.size();

    if (!m_bufferInitialized || m_numChannels != numChannels)
    {
        initializeBuffer(numChannels);
    }

    int startWriteIndex = m_currentIndex % m_maxSamples;

    /* Write incoming samples into the circular buffer.
     * m_currentIndex is a monotonic counter; modulo gives the buffer position. */
    for (int s = 0; s < newSamples; ++s)
    {
        int writeIndex = m_currentIndex % m_maxSamples;

        m_data[0][writeIndex] = static_cast<double>(writeIndex) / m_samplingRate;
        for (int ch = 0; ch < numChannels; ++ch)
        {
            double value = incomingData[ch][s];
            m_data[ch + 1][writeIndex] = value;
            updateMinMaxCache(value);
        }

        m_currentIndex++;
    }

    int endWriteIndex = (m_currentIndex - 1 + m_maxSamples) % m_maxSamples;

    m_writePosition = endWriteIndex;
    emit writePositionChanged();

    /* Write GAP_VALUE ahead of the cursor to create the visual line break.
     * This is what gives the EEG display its characteristic "sweeping" appearance
     * where the cursor erases old data as it moves forward. */
    for (int g = 1; g <= GAP_SIZE; ++g)
    {
        int gapIndex = (endWriteIndex + g) % m_maxSamples;
        for (int ch = 0; ch < numChannels; ++ch)
        {
            m_data[ch + 1][gapIndex] = GAP_VALUE;
        }
    }

    /* Determine the row range that changed for incremental notification.
     * On wraparound (rare), fall back to full-buffer notification. */
    int changedStart, changedEnd;

    if (startWriteIndex <= endWriteIndex)
    {
        changedStart = startWriteIndex;
        changedEnd = std::min(endWriteIndex + GAP_SIZE, m_maxSamples - 1);
    }
    else
    {
        changedStart = 0;
        changedEnd = m_maxSamples - 1;
    }

    emitDataChanged(changedStart, changedEnd);
}

// ============================================================================
// Property Accessors
// ============================================================================

double EegDataModel::minValue() const
{
    /* Returns a safe default (0.0) before any real data has arrived.
     * Once data starts flowing, returns the smallest Y pixel value seen.
     * Note: this cache only grows (monotonic) — it never shrinks, which means
     * the Y-axis range may become overly wide after large transients. */
    if (m_cachedMin == std::numeric_limits<double>::infinity())
    {
        return 0.0;
    }
    return m_cachedMin;
}

double EegDataModel::maxValue() const
{
    /* Returns a safe default (1000.0) before any data arrives.
     * The 1000.0 default provides a reasonable initial chart range
     * for typical channel spacing values. */
    if (m_cachedMax == -std::numeric_limits<double>::infinity())
    {
        return 1000.0;
    }
    return m_cachedMax;
}

int EegDataModel::writePosition() const
{
    return m_writePosition;
}

double EegDataModel::samplingRate() const
{
    return m_samplingRate;
}

void EegDataModel::setSamplingRate(double newSamplingRate)
{
    /* Called by EegBackend::onSamplingRateDetected() once the LSL stream
     * reports its actual hardware sampling rate. This triggers a full buffer
     * reallocation because m_maxSamples depends on the rate. */
    if (newSamplingRate <= 0 || qFuzzyCompare(m_samplingRate, newSamplingRate))
        return;

    m_samplingRate = newSamplingRate;
    emit samplingRateChanged();

    recalculateMaxSamples();
}

double EegDataModel::timeWindowSeconds() const
{
    return m_timeWindowSeconds;
}

void EegDataModel::setTimeWindowSeconds(double newTimeWindowSeconds)
{
    /* Called when the user changes the display time window from the control
     * panel (e.g. 10s → 5s). Triggers buffer reallocation since the number
     * of samples to store changes proportionally. */
    if (newTimeWindowSeconds <= 0 || qFuzzyCompare(m_timeWindowSeconds, newTimeWindowSeconds))
        return;

    m_timeWindowSeconds = newTimeWindowSeconds;
    emit timeWindowSecondsChanged();

    recalculateMaxSamples();
}

int EegDataModel::maxSamples() const
{
    return m_maxSamples;
}

void EegDataModel::recalculateMaxSamples()
{
    int newMaxSamples = static_cast<int>(m_samplingRate * m_timeWindowSeconds);

    if (newMaxSamples < 100)
    {
        newMaxSamples = 100;
    }

    if (m_maxSamples != newMaxSamples)
    {
        qInfo() << "EegDataModel: recalculating maxSamples from" << m_maxSamples
                << "to" << newMaxSamples
                << "(samplingRate:" << m_samplingRate << "Hz,"
                << "timeWindow:" << m_timeWindowSeconds << "s)";

        m_maxSamples = newMaxSamples;
        emit maxSamplesChanged();

        /* Changing the buffer size requires full reinitialization.
         * This discards all current data — acceptable because the time
         * window change implies a new viewing context. */
        if (m_bufferInitialized && m_numChannels > 0)
        {
            m_bufferInitialized = false;
            initializeBuffer(m_numChannels);
        }
    }
}
