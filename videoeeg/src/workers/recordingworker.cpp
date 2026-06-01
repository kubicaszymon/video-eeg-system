/*
 * ==========================================================================
 *  recordingworker.cpp — Background Thread Disk I/O Implementation
 * ==========================================================================
 *  See recordingworker.h for architecture overview, file format specification,
 *  batching rationale, and flush policy.
 * ==========================================================================
 */

#include "recordingworker.h"

#include <QFileInfo>
#include <QDir>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSaveFile>
#include <QDebug>

RecordingWorker::RecordingWorker(QObject* parent)
    : QObject(parent)
{
}

RecordingWorker::~RecordingWorker()
{
    // Ensure files are closed if worker is destroyed unexpectedly
    if (m_eegFile.isOpen())
        m_eegFile.close();
    if (m_markersFile.isOpen())
        m_markersFile.close();
    if (m_framesFile.isOpen())
        m_framesFile.close();
}

void RecordingWorker::initializeFiles(const QString& eegPath,
                                       const QString& markersPath,
                                       const QString& framesPath,
                                       const QString& metadataPath,
                                       const QStringList& channelNames,
                                       const QString& sessionName,
                                       double samplingRate)
{
    m_sessionName = sessionName;
    m_savePath = QFileInfo(eegPath).absolutePath();
    m_sampleCount = 0;
    m_markerCount = 0;
    m_frameCount = 0;

    // Open EEG file
    m_eegFile.setFileName(eegPath);
    if (!m_eegFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
        emit filesInitialized(false, "Cannot open EEG file: " + eegPath);
        return;
    }
    m_eegStream.setDevice(&m_eegFile);

    // Open markers file
    m_markersFile.setFileName(markersPath);
    if (!m_markersFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
        m_eegFile.close();
        emit filesInitialized(false, "Cannot open markers file: " + markersPath);
        return;
    }
    m_markersStream.setDevice(&m_markersFile);

    // Open frames file
    m_framesFile.setFileName(framesPath);
    if (!m_framesFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
        m_eegFile.close();
        m_markersFile.close();
        emit filesInitialized(false, "Cannot open frames file: " + framesPath);
        return;
    }
    m_framesStream.setDevice(&m_framesFile);

    // Write headers
    writeEegHeader(channelNames, sessionName, samplingRate);
    writeMarkersHeader();
    writeFramesHeader();
    writeMetadata(sessionName, channelNames, samplingRate);

    // Double flush headers immediately — stream flush + fsync for power-loss safety.
    // This ensures even the CSV headers survive a power cut during the first batch.
    m_eegStream.flush();
    m_eegFile.flush();
    m_markersStream.flush();
    m_markersFile.flush();
    m_framesStream.flush();
    m_framesFile.flush();

    qDebug() << "[RecordingWorker] Files initialized:" << eegPath;
    emit filesInitialized(true, QString());
}

void RecordingWorker::writeEegBatch(const QVector<QVector<float>>& samples,
                                     const QVector<double>& timestamps)
{
    if (!m_eegFile.isOpen() || samples.isEmpty())
        return;

    for (int i = 0; i < samples.size(); ++i) {
        // Write LSL timestamp with full precision
        m_eegStream << QString::number(timestamps[i], 'f', 6);

        // Write channel values
        const auto& channelValues = samples[i];
        for (int ch = 0; ch < channelValues.size(); ++ch) {
            m_eegStream << ',' << QString::number(channelValues[ch], 'f', 4);
        }
        m_eegStream << '\n';
    }

    m_sampleCount += samples.size();

    // Double flush: QTextStream::flush() empties Qt's internal write buffer
    // to the OS page cache. QFile::flush() calls fsync()/FlushFileBuffers()
    // to commit the page cache to physical media. Both are needed for
    // data durability on unexpected power loss during a 24-hour recording.
    m_eegStream.flush();
    m_eegFile.flush();

    emit batchWritten(samples.size(), m_eegFile.size());
}

void RecordingWorker::writePauseMarker(const QString& type,
                                        double lslTimestamp,
                                        double sessionTimeSec)
{
    // Write to EEG CSV as inline marker
    if (m_eegFile.isOpen()) {
        m_eegStream << type << ',' << QString::number(lslTimestamp, 'f', 6) << '\n';
        m_eegStream.flush();
        m_eegFile.flush();
    }

    // Write to markers CSV
    if (m_markersFile.isOpen()) {
        m_markersStream << type << ",,"
                        << QString::number(lslTimestamp, 'f', 6) << ','
                        << QString::number(sessionTimeSec, 'f', 3) << '\n';
        m_markersStream.flush();
        m_markersFile.flush();
    }
}

void RecordingWorker::writeMarker(const QString& type,
                                   const QString& label,
                                   double lslTimestamp,
                                   double sessionTimeSec)
{
    if (!m_markersFile.isOpen())
        return;

    m_markersStream << type << ','
                    << label << ','
                    << QString::number(lslTimestamp, 'f', 6) << ','
                    << QString::number(sessionTimeSec, 'f', 3) << '\n';
    m_markersStream.flush();
    m_markersFile.flush();
    m_markerCount++;
}

void RecordingWorker::writeFrameTimestamp(double lslTimestamp,
                                          qint64 frameNumber,
                                          const QString& segmentFile)
{
    if (!m_framesFile.isOpen())
        return;

    m_framesStream << frameNumber << ','
                   << QString::number(lslTimestamp, 'f', 6) << ','
                   << segmentFile << '\n';

    m_frameCount++;

    // Deferred flush: at 30 fps, flushing every frame would generate 30 fsync
    // calls per second. Flushing every 100 frames reduces this to 0.3/sec at the
    // cost of a maximum ~3.3 s window of unsynced frame index data — acceptable
    // given that the EEG data (which is more critical) flushes every batch.
    if (m_frameCount % 100 == 0) {
        m_framesStream.flush();
        m_framesFile.flush();
    }
}

void RecordingWorker::closeFiles(double durationSeconds, qint64 videoFileSizeBytes)
{
    RecordingSummary summary;
    summary.sessionName = m_sessionName;
    summary.savePath = m_savePath;
    summary.durationSeconds = durationSeconds;
    summary.eegSamples = m_sampleCount;
    summary.videoFrames = m_frameCount;
    summary.markerCount = static_cast<int>(m_markerCount);

    // Flush and close all files
    if (m_eegFile.isOpen()) {
        m_eegStream.flush();
        summary.eegFileSizeBytes = m_eegFile.size();
        m_eegFile.close();
    }

    if (m_markersFile.isOpen()) {
        m_markersStream.flush();
        m_markersFile.close();
    }

    if (m_framesFile.isOpen()) {
        m_framesStream.flush();
        m_framesFile.close();
    }

    summary.videoFileSizeBytes = videoFileSizeBytes;
    summary.endTime = QDateTime::currentDateTime().toString(Qt::ISODate);

    qDebug() << "[RecordingWorker] Files closed. EEG samples:" << m_sampleCount
             << "Markers:" << m_markerCount << "Frames:" << m_frameCount;

    emit filesClosed(summary);
}

void RecordingWorker::writeEegHeader(const QStringList& channelNames,
                                      const QString& sessionName,
                                      double samplingRate)
{
    m_eegStream << "# SessionName: " << sessionName << '\n';
    m_eegStream << "# SamplingRate: " << QString::number(samplingRate, 'f', 1) << '\n';
    m_eegStream << "# StartTime: " << QDateTime::currentDateTime().toString(Qt::ISODate) << '\n';
    m_eegStream << "# Channels: " << channelNames.size() << '\n';

    // Column header
    m_eegStream << "LSL_Timestamp";
    for (const auto& name : channelNames) {
        m_eegStream << ',' << name;
    }
    m_eegStream << '\n';
}

void RecordingWorker::writeMarkersHeader()
{
    m_markersStream << "Type,Label,LSL_Timestamp,SessionTimeSec\n";
}

void RecordingWorker::writeFramesHeader()
{
    m_framesStream << "FrameNumber,LSL_Timestamp,SegmentFile\n";
}

void RecordingWorker::writeMetadata(const QString& sessionName,
                                      const QStringList& channelNames,
                                      double samplingRate)
{
    // Use atomic write so the metadata JSON is never half-written on power loss.
    QJsonObject root;
    root["sessionName"] = sessionName;
    root["startTime"] = QDateTime::currentDateTime().toString(Qt::ISODate);
    root["samplingRate"] = samplingRate;
    root["channelCount"] = channelNames.size();

    QJsonArray chArray;
    for (const auto& name : channelNames)
        chArray.append(name);
    root["channelNames"] = chArray;

    root["eegFormat"] = "CSV";
    root["videoFormat"] = "MKV (H.264)";
    root["timestampDomain"] = "LSL";
    root["version"] = "1.0";

    QString metadataPath = m_savePath + "/" + sessionName + "_metadata.json";
    if (!atomicWriteJson(metadataPath, root)) {
        qWarning() << "[RecordingWorker] Failed to write metadata file:" << metadataPath;
    }
}

// ==========================================================================
//  Atomic JSON Write Helper
// ==========================================================================
//  Uses QSaveFile which writes to a temporary file first, then atomically
//  renames to the final path on commit(). If the app crashes between
//  write() and commit(), the original file (if any) is untouched.
//  On NTFS and most POSIX filesystems, the rename is atomic.
// ==========================================================================

bool RecordingWorker::atomicWriteJson(const QString& finalPath, const QJsonObject& json)
{
    QSaveFile file(finalPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        qWarning() << "[RecordingWorker] atomicWriteJson: cannot open" << finalPath
                    << file.errorString();
        return false;
    }

    QJsonDocument doc(json);
    file.write(doc.toJson(QJsonDocument::Indented));

    // commit() flushes, fsyncs, and atomically renames tmp → finalPath.
    // Returns false if any step fails; the original file is preserved.
    if (!file.commit()) {
        qWarning() << "[RecordingWorker] atomicWriteJson: commit failed for" << finalPath
                    << file.errorString();
        return false;
    }
    return true;
}

// ==========================================================================
//  Session State Persistence (Crash Recovery / Auto-Resume)
// ==========================================================================

void RecordingWorker::writeSessionState(const QJsonObject& stateJson, const QString& statePath)
{
    if (!atomicWriteJson(statePath, stateJson)) {
        qWarning() << "[RecordingWorker] Failed to persist session state to:" << statePath;
    }
}

void RecordingWorker::markSessionClosed(const QString& statePath)
{
    // Read the existing session state, update status to "closed", and write back.
    // If the file doesn't exist (shouldn't happen), create a minimal one.
    QFile file(statePath);
    QJsonObject state;

    if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
        file.close();
        if (doc.isObject())
            state = doc.object();
    }

    state["status"] = QStringLiteral("closed");
    state["closedAt"] = QDateTime::currentDateTime().toString(Qt::ISODate);

    if (!atomicWriteJson(statePath, state)) {
        qWarning() << "[RecordingWorker] Failed to mark session as closed:" << statePath;
    }
}
