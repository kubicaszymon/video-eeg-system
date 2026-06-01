/*
 * ==========================================================================
 *  amplifiermodel.h — EEG Amplifier Metadata Model
 * ==========================================================================
 *
 *  PURPOSE:
 *    Plain data structure (POD) representing a single EEG amplifier device
 *    as discovered by the Svarog Streamer external process. Holds the device
 *    identity and its hardware capabilities (channels, sampling rates).
 *
 *  DESIGN PATTERN:
 *    Value type — no behavior, no ownership. Passed by value/copy in QList.
 *
 *  DATA FLOW:
 *    Svarog Streamer stdout  ──parse──▸  AmplifierManager::m_amplifiers (QList<Amplifier>)
 *                                             │
 *                                             ├──▸ AmplifierSetupBackend (QML device picker)
 *                                             └──▸ EegBackend::channelNames() (label lookup)
 *
 *  FIELD SEMANTICS:
 *    name                – Human-readable device name from Svarog output (e.g. "Perun32")
 *    id                  – Machine-readable identifier used to launch streaming (e.g. "usb:002/005")
 *    available_channels  – Flat list of channel labels (e.g. ["Fp1", "Fp2", "C3", ...])
 *    available_samplings – Flat list of supported sampling rates as strings (e.g. ["256", "512"])
 *
 * ==========================================================================
 */

#ifndef AMPLIFIERMODEL_H
#define AMPLIFIERMODEL_H

#include <QStringList>

struct Amplifier
{
    QString name;
    QString id;
    QStringList available_channels;
    QStringList available_samplings;
};

#endif // AMPLIFIERMODEL_H
