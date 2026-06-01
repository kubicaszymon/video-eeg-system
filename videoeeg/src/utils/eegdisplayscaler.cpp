/*
 * ==========================================================================
 *  eegdisplayscaler.cpp — EEG Signal Scaling Implementation
 * ==========================================================================
 *  See eegdisplayscaler.h for architecture overview, formulas, and
 *  data transposition rationale.
 * ==========================================================================
 */

#include "eegdisplayscaler.h"
#include <QtMath>
#include <QDebug>

const QList<double> EegDisplayScaler::SENSITIVITY_OPTIONS = {
    1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0
};

EegDisplayScaler::EegDisplayScaler(QObject *parent)
    : QObject(parent)
{
}

double EegDisplayScaler::displayGain() const
{
    /*
     * G [px/μV] = DPI / (25.4 × Sensitivity[μV/mm])
     *
     * Dimensional analysis:
     *   [px/inch] / ([mm/inch] × [μV/mm]) = [px/μV]
     *
     * Example: 96 DPI, 7 μV/mm sensitivity:
     *   G = 96 / (25.4 × 7) = 0.54 px/μV
     *   A 70 μV signal spans 37.8 px ≈ 1 cm on screen (correct!)
     */
    return m_screenDpi / (MM_PER_INCH * m_sensitivity);
}

void EegDisplayScaler::setSensitivity(double sensitivity)
{
    /* Validates against the predefined clinical sensitivity steps.
     * Rejecting arbitrary values prevents non-standard displays that
     * would be confusing for clinicians accustomed to standard gains. */
    if (!SENSITIVITY_OPTIONS.contains(sensitivity))
    {
        qWarning() << "[EegDisplayScaler] Invalid sensitivity:" << sensitivity
                   << "μV/mm. Valid options:" << SENSITIVITY_OPTIONS;
        return;
    }

    if (qFuzzyCompare(m_sensitivity, sensitivity))
        return;

    m_sensitivity = sensitivity;

    /* Both signals must be emitted because changing sensitivity recalculates
     * the display gain (which depends on sensitivity). QML bindings on both
     * properties will be updated. */
    emit sensitivityChanged();
    emit displayGainChanged();

    qDebug() << "[EegDisplayScaler] Sensitivity:" << m_sensitivity
             << "μV/mm, displayGain:" << displayGain() << "px/μV";
}

void EegDisplayScaler::setScreenDpi(double dpi)
{
    /* Screen DPI affects the physical accuracy of the display. Typically
     * set once at startup from Screen.pixelDensity in QML. Changing DPI
     * also recalculates the display gain since G depends on DPI. */
    if (dpi <= 0)
    {
        qWarning() << "[EegDisplayScaler] Invalid DPI:" << dpi;
        return;
    }

    if (qFuzzyCompare(m_screenDpi, dpi))
        return;

    m_screenDpi = dpi;
    emit screenDpiChanged();
    emit displayGainChanged();

    qDebug() << "[EegDisplayScaler] Screen DPI:" << m_screenDpi
             << ", displayGain:" << displayGain() << "px/μV";
}

double EegDisplayScaler::transformSample(double rawValueMicrovolts, double baselineOffset) const
{
    /* Subtract from baseline: positive μV deflects upward on screen,
     * compensating for Qt's downward-increasing Y-axis. */
    return baselineOffset - (rawValueMicrovolts * displayGain());
}

double EegDisplayScaler::calculateChannelOffset(int channelIndex, int totalChannels, double channelSpacing)
{
    /* Channel 0 gets the highest offset (top of the plot area),
     * last channel gets offset 0 (bottom). This mirrors the clinical
     * EEG montage convention where Fp1/Fp2 appear at the top. */
    return (totalChannels - 1 - channelIndex) * channelSpacing;
}

QVector<QVector<double>> EegDisplayScaler::transformChunk(
    const std::vector<std::vector<float>>& chunk,
    const QVector<int>& channelIndices,
    double channelSpacing) const
{
    if (chunk.empty() || chunk[0].empty())
    {
        return {};
    }

    const int numSamples = static_cast<int>(chunk.size());
    const int numChannels = channelIndices.size();
    const int totalChunkChannels = static_cast<int>(chunk[0].size());
    const double gain = displayGain();

    /* Output layout: [channel][sample] — transposed from input [sample][channel].
     * This layout matches EegDataModel's column-per-channel storage. */
    QVector<QVector<double>> result(numChannels);

    for (int ch = 0; ch < numChannels; ++ch)
    {
        result[ch].reserve(numSamples);

        const int sourceChannel = channelIndices[ch];

        if (sourceChannel < 0 || sourceChannel >= totalChunkChannels)
        {
            /* Out-of-range channel index — fill with flat baseline.
             * This can happen if the user selects more channels than
             * the amplifier provides. */
            double offset = calculateChannelOffset(ch, numChannels, channelSpacing);
            for (int s = 0; s < numSamples; ++s)
            {
                result[ch].append(offset);
            }
            continue;
        }

        const double offset = calculateChannelOffset(ch, numChannels, channelSpacing);

        for (int s = 0; s < numSamples; ++s)
        {
            const double rawValue = static_cast<double>(chunk[s][sourceChannel]);
            const double scaledValue = offset - (rawValue * gain);
            result[ch].append(scaledValue);
        }
    }

    return result;
}
