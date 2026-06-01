/*
 * ==========================================================================
 *  eegdisplayscaler.h — Physically-Calibrated EEG Signal Scaling
 * ==========================================================================
 *
 *  PURPOSE:
 *    Transforms raw EEG values (in microvolts) into pixel coordinates for
 *    on-screen rendering. Implements the clinical EEG sensitivity model
 *    where gain is expressed in μV/mm, ensuring that signal amplitudes
 *    on screen correspond to real physical measurements when viewed on
 *    a correctly-calibrated monitor.
 *
 *  DESIGN PATTERN:
 *    Strategy — owned by EegBackend, can be swapped or reconfigured at
 *    runtime via QML property bindings (sensitivity, screenDpi).
 *    Stateless transform: all methods are const; the scaler holds only
 *    configuration, not data.
 *
 *  CORE FORMULAS:
 *
 *    Display Gain:
 *      G [px/μV] = DPI / (25.4 × Sensitivity[μV/mm])
 *
 *    Sample Transform (Y-axis inversion for Qt coordinate system):
 *      Y_pixel = baseline_offset - (raw_μV × G)
 *
 *    Channel Layout (top-to-bottom):
 *      baseline_offset(ch) = (totalChannels - 1 - ch) × channelSpacing
 *
 *  WHY Y-AXIS INVERSION:
 *    In Qt/QML, the Y-axis increases downward (0 at top, max at bottom).
 *    In clinical EEG convention, positive voltage deflects upward.
 *    Subtracting from baseline achieves the correct visual orientation.
 *
 *  DATA FLOW:
 *    AmplifierManager::dataReceived  →  EegBackend::onDataReceived()
 *                                            │
 *                                            ▼
 *                                    EegDisplayScaler::transformChunk()
 *                                            │
 *                                    Input:  [sample][channel] float μV
 *                                    Output: [channel][sample] double pixels
 *                                            │
 *                                            ▼
 *                                    EegDataModel::updateAllData()
 *                                            │
 *                                            ▼
 *                                    EegGraph.qml (renders waveforms)
 *
 *  NOTE ON DATA TRANSPOSITION:
 *    Input from LSL is [sample][channel] (row-major, time-first).
 *    Output for display is [channel][sample] (column-major, channel-first).
 *    This transposition happens in transformChunk() and is required because
 *    EegDataModel stores data per-channel in its circular buffer columns.
 *
 * ==========================================================================
 */

#ifndef EEGDISPLAYSCALER_H
#define EEGDISPLAYSCALER_H

#include <QObject>
#include <QList>
#include <QVector>
#include <QtQml/qqmlregistration.h>

class EegDisplayScaler : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(double sensitivity READ sensitivity WRITE setSensitivity NOTIFY sensitivityChanged FINAL)
    Q_PROPERTY(QList<double> sensitivityOptions READ sensitivityOptions CONSTANT FINAL)
    Q_PROPERTY(double screenDpi READ screenDpi WRITE setScreenDpi NOTIFY screenDpiChanged FINAL)
    Q_PROPERTY(double displayGain READ displayGain NOTIFY displayGainChanged FINAL)

public:
    explicit EegDisplayScaler(QObject *parent = nullptr);

    /* Standard clinical EEG sensitivity steps in μV/mm.
     * Range covers from very high gain (1 μV/mm, epilepsy monitoring)
     * to very low gain (100 μV/mm, artifact-heavy signals). */
    static const QList<double> SENSITIVITY_OPTIONS;

    static constexpr double MM_PER_INCH = 25.4;
    static constexpr double DEFAULT_DPI = 96.0;
    static constexpr double DEFAULT_SENSITIVITY = 10.0;  // μV/mm

    double sensitivity() const { return m_sensitivity; }
    double screenDpi() const { return m_screenDpi; }
    double displayGain() const;
    QList<double> sensitivityOptions() const { return SENSITIVITY_OPTIONS; }

    void setSensitivity(double sensitivity);
    void setScreenDpi(double dpi);

    /* Single-sample transform: μV → pixel Y-coordinate.
     * baselineOffset is the Y position of the channel's zero line. */
    double transformSample(double rawValueMicrovolts, double baselineOffset) const;

    /* Bulk transform for an entire LSL chunk.
     * Performs channel extraction (via channelIndices), μV→px scaling,
     * Y-axis inversion, and data transposition in a single pass. */
    QVector<QVector<double>> transformChunk(
        const std::vector<std::vector<float>>& chunk,
        const QVector<int>& channelIndices,
        double channelSpacing) const;

    /* Calculates the Y-pixel baseline for a given channel.
     * Channel 0 is placed at the top; channels stack downward. */
    static double calculateChannelOffset(int channelIndex, int totalChannels, double channelSpacing);

signals:
    void sensitivityChanged();
    void screenDpiChanged();
    void displayGainChanged();

private:
    double m_sensitivity = DEFAULT_SENSITIVITY;
    double m_screenDpi = DEFAULT_DPI;
};

#endif // EEGDISPLAYSCALER_H
