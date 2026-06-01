/*
 * ==========================================================================
 *  eegsyncmanager.cpp — EEG-Video Synchronization Buffer Implementation
 * ==========================================================================
 *  See eegsyncmanager.h for architecture overview, clock drift explanation,
 *  buffer sizing rationale, threading model, timestamp validation, and
 *  session tracking.
 *
 *  KEY IMPLEMENTATION NOTES:
 *
 *  getEEGForFrame() — THE SYNCHRONIZATION QUERY
 *    1. Increments m_totalQueryCount for per-session diagnostics.
 *    2. Applies time_correction() to convert video timestamp to EEG clock base.
 *    3. Validates that the adjusted timestamp falls within the buffer range.
 *       If not, sets "outOfRange"=true with the distance to the nearest
 *       boundary in milliseconds ("rangeErrorMs"). This catches cases where:
 *         - Video started before EEG (timestamp < oldest EEG sample)
 *         - EEG stream is lagging behind video (timestamp > newest EEG sample)
 *         - Buffer sizes are mismatched (now fixed: both are 30 seconds)
 *    4. Performs interpolation (nearest neighbor or linear) and returns
 *       the matched sample with its offset from the query timestamp.
 *
 *  markSessionStart() / markSessionEnd()
 *    Called by RecordingManager at session boundaries. Resets diagnostic
 *    counters and logs a per-session synchronization quality summary.
 *
 *  isTimestampInRange()
 *    Lightweight O(1) pre-check that callers can use before getEEGForFrame()
 *    to avoid wasting cycles on guaranteed-fail queries.
 *
 * ==========================================================================
 */

#include "eegsyncmanager.h"
#include <QDebug>
#include <QMutexLocker>
#include <QQmlEngine>
#include <algorithm>
#include <cmath>

EegSyncManager* EegSyncManager::s_instance = nullptr;

EegSyncManager::EegSyncManager(QObject* parent)
    : QObject(parent)
{
    s_instance = this;

    // Periodic LSL time_correction() refresh — 10 s interval balances
    // accuracy (short-term drift stays < 1 ms) with the ~100 ms blocking
    // cost of each time_correction() call.
    m_timeCorrectionTimer = new QTimer(this);
    m_timeCorrectionTimer->setInterval(10000);
    connect(m_timeCorrectionTimer, &QTimer::timeout, this, &EegSyncManager::updateTimeCorrection);

    // Throttle QML property notifications to 4 Hz. The buffer is updated
    // at ~50 Hz (EEG data rate); re-rendering the monitoring panel at the
    // same rate would waste CPU on UI that only humans read.
    m_statsTimer = new QTimer(this);
    m_statsTimer->setInterval(250);
    connect(m_statsTimer, &QTimer::timeout, this, &EegSyncManager::statsChanged);
    m_statsTimer->start();

    qInfo() << "[EegSyncManager] Created";
}

EegSyncManager::~EegSyncManager()
{
    if (s_instance == this)
        s_instance = nullptr;
    qInfo() << "[EegSyncManager] Destroyed";
}

EegSyncManager* EegSyncManager::instance()
{
    if (!s_instance)
        s_instance = new EegSyncManager();
    return s_instance;
}

EegSyncManager* EegSyncManager::create(QQmlEngine* qmlEngine, QJSEngine* jsEngine)
{
    Q_UNUSED(jsEngine)
    auto* inst = instance();
    // CppOwnership: QML engine must not delete this singleton
    QJSEngine::setObjectOwnership(inst, QJSEngine::CppOwnership);
    return inst;
}

// ============================================================================
// Data Input
// ============================================================================

void EegSyncManager::addEegSamples(const std::vector<std::vector<float>>& chunk,
                                    const std::vector<double>& timestamps,
                                    const QVector<int>& channelIndices)
{
    if (chunk.empty() || timestamps.empty())
        return;

    // LSL guarantees chunk.size() == timestamps.size(), but guard defensively
    const int count = static_cast<int>(std::min(chunk.size(), timestamps.size()));

    QMutexLocker locker(&m_mutex);

    for (int i = 0; i < count; ++i)
    {
        const auto& sample = chunk[i];

        // Store only the selected channels to reduce memory footprint.
        // A 64-channel amplifier produces 64× the data of 8 displayed channels;
        // storing all channels would waste ~8× buffer capacity and increase
        // copy overhead on every query.
        std::vector<float> selected;
        if (channelIndices.isEmpty())
        {
            selected = sample;
        }
        else
        {
            selected.reserve(channelIndices.size());
            for (int idx : channelIndices)
            {
                if (idx >= 0 && idx < static_cast<int>(sample.size()))
                    selected.push_back(sample[idx]);
                else
                    selected.push_back(0.0f); // Guard against out-of-range indices
            }
        }

        m_buffer.emplace_back(timestamps[i], std::move(selected));
    }

    // Enforce rolling window: pop oldest samples when over capacity.
    // pop_front on std::deque is O(1), making this very cheap.
    while (static_cast<int>(m_buffer.size()) > m_maxBufferSize)
        m_buffer.pop_front();
}

// ============================================================================
// Synchronization Queries
// ============================================================================

QVariantMap EegSyncManager::getEEGForFrame(double videoTimestamp) const
{
    QVariantMap result;
    result["valid"] = false;
    result["outOfRange"] = false;

    QMutexLocker locker(&m_mutex);

    m_totalQueryCount++;

    if (m_buffer.empty() || videoTimestamp <= 0.0)
        return result;

    // Subtract the drift correction offset to convert the video timestamp
    // from the PC clock base to the EEG device's LSL clock base.
    // Without this, the search would look for a time that does not exist
    // in the EEG buffer when the two clocks diverge.
    double adjustedTs = videoTimestamp - m_timeCorrection;

    // --- Timestamp range validation ---
    // Check whether the query timestamp falls within the buffer's time range.
    // A tolerance of one inter-sample interval (1/samplingRate) is applied to
    // account for floating-point rounding at the buffer boundaries. Queries
    // outside this range indicate that the video and EEG streams are not
    // overlapping in time — the caller should check "outOfRange" in the result.
    double oldest = m_buffer.front().lslTimestamp;
    double newest = m_buffer.back().lslTimestamp;
    double tolerance = (m_samplingRate > 0.0) ? (1.0 / m_samplingRate) : 0.004;

    if (adjustedTs < oldest - tolerance || adjustedTs > newest + tolerance)
    {
        m_outOfRangeCount++;

        // Calculate how far outside the buffer the timestamp is, so the
        // caller can display a meaningful diagnostic ("EEG data is 200ms behind").
        double rangeErrorMs = 0.0;
        if (adjustedTs < oldest)
            rangeErrorMs = (oldest - adjustedTs) * 1000.0;
        else
            rangeErrorMs = (adjustedTs - newest) * 1000.0;

        result["outOfRange"] = true;
        result["rangeErrorMs"] = rangeErrorMs;

        // Still attempt to return the nearest boundary sample so the caller
        // has something to display, but mark it as out-of-range.
        // Only log a warning once per 100 occurrences to avoid log spam.
        if (m_outOfRangeCount % 100 == 1)
        {
            qDebug() << "[EegSyncManager] Query out of range:"
                     << "videoTs=" << videoTimestamp
                     << "adjusted=" << adjustedTs
                     << "buffer=[" << oldest << "," << newest << "]"
                     << "errorMs=" << rangeErrorMs
                     << "count=" << m_outOfRangeCount;
        }
    }

    EegTimestampedSample sample = (m_interpolationMode == 1)
        ? linearInterpolate(adjustedTs)
        : nearestNeighbor(adjustedTs);

    if (!sample.isValid())
        return result;

    double offsetMs = std::abs(adjustedTs - sample.lslTimestamp) * 1000.0;
    m_lastSyncOffsetMs = offsetMs;
    updateRunningAverage(offsetMs);

    result["valid"] = true;
    result["timestamp"] = sample.lslTimestamp;
    result["offsetMs"] = offsetMs;

    QVariantList channels;
    channels.reserve(static_cast<int>(sample.channels.size()));
    for (float val : sample.channels)
        channels.append(static_cast<double>(val));
    result["channels"] = channels;

    return result;
}

QVariantList EegSyncManager::getEEGRangeForFrame(double startTs, double endTs) const
{
    QVariantList results;

    QMutexLocker locker(&m_mutex);

    if (m_buffer.empty() || startTs >= endTs)
        return results;

    double adjustedStart = startTs - m_timeCorrection;
    double adjustedEnd   = endTs   - m_timeCorrection;

    // Binary search to jump directly to the first sample in range — O(log N)
    // rather than scanning from the front of the buffer.
    auto itStart = std::lower_bound(
        m_buffer.begin(), m_buffer.end(), adjustedStart,
        [](const EegTimestampedSample& s, double ts) { return s.lslTimestamp < ts; });

    for (auto it = itStart; it != m_buffer.end() && it->lslTimestamp <= adjustedEnd; ++it)
    {
        QVariantMap entry;
        entry["timestamp"] = it->lslTimestamp;
        QVariantList channels;
        for (float val : it->channels)
            channels.append(static_cast<double>(val));
        entry["channels"] = channels;
        results.append(entry);
    }

    return results;
}

// ============================================================================
// Interpolation Algorithms
// ============================================================================

EegTimestampedSample EegSyncManager::nearestNeighbor(double adjustedTs) const
{
    // std::lower_bound returns an iterator to the first element >= adjustedTs.
    // We then compare it with the previous element to find the true nearest.
    auto it = std::lower_bound(
        m_buffer.begin(), m_buffer.end(), adjustedTs,
        [](const EegTimestampedSample& s, double ts) { return s.lslTimestamp < ts; });

    if (it == m_buffer.end())   return m_buffer.back();
    if (it == m_buffer.begin()) return m_buffer.front();

    auto prevIt = std::prev(it);
    double diffCurrent = std::abs(it->lslTimestamp - adjustedTs);
    double diffPrev    = std::abs(prevIt->lslTimestamp - adjustedTs);

    return (diffPrev < diffCurrent) ? *prevIt : *it;
}

EegTimestampedSample EegSyncManager::linearInterpolate(double adjustedTs) const
{
    auto it = std::lower_bound(
        m_buffer.begin(), m_buffer.end(), adjustedTs,
        [](const EegTimestampedSample& s, double ts) { return s.lslTimestamp < ts; });

    // At the edges of the buffer there is no bracketing pair — fall back
    // to the boundary sample rather than extrapolating beyond known data.
    if (it == m_buffer.end())   return m_buffer.back();
    if (it == m_buffer.begin()) return m_buffer.front();

    auto prevIt = std::prev(it);

    double dt = it->lslTimestamp - prevIt->lslTimestamp;
    if (dt <= 0.0) return *prevIt; // Degenerate case: duplicate timestamps

    // alpha ∈ [0, 1]: how far adjustedTs is between prevIt and it
    double alpha = std::clamp((adjustedTs - prevIt->lslTimestamp) / dt, 0.0, 1.0);

    const auto& chA = prevIt->channels;
    const auto& chB = it->channels;
    int numCh = static_cast<int>(std::min(chA.size(), chB.size()));

    std::vector<float> interpolated(numCh);
    for (int i = 0; i < numCh; ++i)
        interpolated[i] = static_cast<float>(chA[i] * (1.0 - alpha) + chB[i] * alpha);

    // Reference timestamp: use whichever boundary is closer so that
    // the returned offsetMs calculation in getEEGForFrame() is meaningful.
    double refTs = (alpha < 0.5) ? prevIt->lslTimestamp : it->lslTimestamp;

    return EegTimestampedSample(refTs, std::move(interpolated));
}

// ============================================================================
// Clock Drift Correction
// ============================================================================

void EegSyncManager::setLslInlet(lsl::stream_inlet* inlet)
{
    m_lslInlet = inlet;

    if (inlet)
    {
        updateTimeCorrection(); // Get an initial correction immediately
        m_timeCorrectionTimer->start();
        qInfo() << "[EegSyncManager] LSL inlet set, time correction timer started";
    }
    else
    {
        m_timeCorrectionTimer->stop();
    }
}

void EegSyncManager::updateTimeCorrection()
{
    if (!m_lslInlet)
        return;

    try
    {
        m_prevTimeCorrection = m_timeCorrection;

        // time_correction() blocks for up to 1 s while performing a
        // network round-trip to the LSL transmitter. This is acceptable
        // at a 10 s polling interval but must not be called on the hot path.
        m_timeCorrection   = m_lslInlet->time_correction(1.0);
        m_timeCorrectionMs = m_timeCorrection;

        // Drift = how much the correction changed since the last update.
        // Persistent drift indicates that the two clocks are running at
        // measurably different rates (expected for USB devices: ~±50 ppm).
        double delta = (m_timeCorrection - m_prevTimeCorrection) * 1000.0; // ms
        m_clockDriftMs = delta;

        qDebug() << "[EegSyncManager] Time correction:" << m_timeCorrection * 1000.0
                 << "ms, drift:" << delta << "ms";
    }
    catch (const std::exception& e)
    {
        qWarning() << "[EegSyncManager] time_correction() failed:" << e.what();
    }
}

// ============================================================================
// Configuration
// ============================================================================

void EegSyncManager::setInterpolationMode(int mode)
{
    m_interpolationMode = (mode == 1) ? 1 : 0;
}

void EegSyncManager::clearBuffer()
{
    QMutexLocker locker(&m_mutex);
    m_buffer.clear();
    m_lastSyncOffsetMs  = 0.0;
    m_avgSyncOffsetMs   = 0.0;
    m_offsetSampleCount = 0;
    m_offsetSum         = 0.0;
    emit statsChanged();
}

void EegSyncManager::setSamplingRate(double rate)
{
    if (rate <= 0.0 || qFuzzyCompare(m_samplingRate, rate))
        return;

    m_samplingRate = rate;

    // Resize buffer to hold exactly 30 s of data at the actual rate.
    // This must be done dynamically because the nominal rate in the LSL
    // stream metadata sometimes differs from the actual hardware rate.
    m_maxBufferSize = static_cast<int>(rate * 30.0);
    emit maxBufferSizeChanged();
    emit samplingRateChanged();

    qInfo() << "[EegSyncManager] Sampling rate:" << rate
            << "Hz, buffer:" << m_maxBufferSize << "samples"
            << ", samples/frame:" << samplesPerFrame();
}

double EegSyncManager::samplesPerFrame() const
{
    return (m_videoFps > 0.0) ? (m_samplingRate / m_videoFps) : 0.0;
}

void EegSyncManager::setMaxBufferSize(int size)
{
    if (size <= 0 || size == m_maxBufferSize)
        return;

    m_maxBufferSize = size;
    emit maxBufferSizeChanged();

    QMutexLocker locker(&m_mutex);
    while (static_cast<int>(m_buffer.size()) > m_maxBufferSize)
        m_buffer.pop_front();
}

// ============================================================================
// Stats / Health
// ============================================================================

int EegSyncManager::bufferSize() const
{
    QMutexLocker locker(&m_mutex);
    return static_cast<int>(m_buffer.size());
}

double EegSyncManager::oldestTimestamp() const
{
    QMutexLocker locker(&m_mutex);
    return m_buffer.empty() ? 0.0 : m_buffer.front().lslTimestamp;
}

double EegSyncManager::newestTimestamp() const
{
    QMutexLocker locker(&m_mutex);
    return m_buffer.empty() ? 0.0 : m_buffer.back().lslTimestamp;
}

double EegSyncManager::bufferDurationSec() const
{
    QMutexLocker locker(&m_mutex);
    if (m_buffer.size() < 2) return 0.0;
    return m_buffer.back().lslTimestamp - m_buffer.front().lslTimestamp;
}

QString EegSyncManager::healthStatus() const
{
    if (m_lastSyncOffsetMs > 15.0) return QStringLiteral("DESYNC");
    if (m_lastSyncOffsetMs >  5.0) return QStringLiteral("WARNING");
    return QStringLiteral("SYNCED");
}

void EegSyncManager::updateRunningAverage(double offsetMs) const
{
    m_offsetSum += offsetMs;
    m_offsetSampleCount++;

    // Compute running average continuously, and reset the accumulator once
    // the window is full to avoid floating-point precision degradation over
    // long recording sessions.
    m_avgSyncOffsetMs = m_offsetSum / m_offsetSampleCount;

    if (m_offsetSampleCount >= RUNNING_AVG_WINDOW)
    {
        m_offsetSum         = 0.0;
        m_offsetSampleCount = 0;
    }
}

// ============================================================================
// Session Tracking
// ============================================================================

void EegSyncManager::markSessionStart()
{
    m_sessionStartTime = lsl::local_clock();
    m_outOfRangeCount  = 0;
    m_totalQueryCount  = 0;
    emit sessionStartTimeChanged();

    qInfo() << "[EegSyncManager] Session started at LSL time:" << m_sessionStartTime;
}

void EegSyncManager::markSessionEnd()
{
    qInfo() << "[EegSyncManager] Session ended. Queries:" << m_totalQueryCount
            << "Out-of-range:" << m_outOfRangeCount
            << "(" << (m_totalQueryCount > 0
                       ? QString::number(100.0 * m_outOfRangeCount / m_totalQueryCount, 'f', 1) + "%"
                       : "N/A")
            << ")";

    m_sessionStartTime = 0.0;
    m_outOfRangeCount  = 0;
    m_totalQueryCount  = 0;
    emit sessionStartTimeChanged();
}

bool EegSyncManager::isTimestampInRange(double videoTimestamp) const
{
    QMutexLocker locker(&m_mutex);

    if (m_buffer.empty() || videoTimestamp <= 0.0)
        return false;

    double adjustedTs = videoTimestamp - m_timeCorrection;
    double oldest     = m_buffer.front().lslTimestamp;
    double newest     = m_buffer.back().lslTimestamp;

    // Tolerance: one inter-sample interval prevents false negatives
    // at the exact buffer boundaries due to floating-point imprecision.
    double tolerance = (m_samplingRate > 0.0) ? (1.0 / m_samplingRate) : 0.004;

    return (adjustedTs >= oldest - tolerance) && (adjustedTs <= newest + tolerance);
}
