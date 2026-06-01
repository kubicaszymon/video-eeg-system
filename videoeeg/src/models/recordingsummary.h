/*
 * ==========================================================================
 *  recordingsummary.h — Post-Recording Session Summary
 * ==========================================================================
 *
 *  PURPOSE:
 *    Value object populated by RecordingWorker::closeFiles() after all disk
 *    I/O is complete. Passed via the filesClosed() signal (cross-thread)
 *    back to RecordingManager, which decomposes it into the
 *    recordingStopped() signal for QML to display in the summary dialog.
 *
 *  DESIGN PATTERN:
 *    Data Transfer Object (Q_GADGET) — crosses the worker→main thread
 *    boundary via Qt::QueuedConnection. Q_GADGET is required so the type
 *    can be registered with qRegisterMetaType<RecordingSummary>() and
 *    queued signal delivery copies it by value safely.
 *
 *  NOTE ON FILE SIZES:
 *    eegFileSizeBytes is taken from QFile::size() at close time on the
 *    worker thread (accurate). videoFileSizeBytes is measured by summing
 *    all segment file sizes from the main thread in stopRecording() —
 *    this is the best we can do since QMediaRecorder does not expose the
 *    ongoing file size during recording.
 *
 * ==========================================================================
 */

#ifndef RECORDINGSUMMARY_H
#define RECORDINGSUMMARY_H

#include <QString>
#include <QObject>

struct RecordingSummary
{
    Q_GADGET

    Q_PROPERTY(QString sessionName     MEMBER sessionName)
    Q_PROPERTY(QString savePath        MEMBER savePath)
    Q_PROPERTY(double  durationSeconds MEMBER durationSeconds)
    Q_PROPERTY(qint64  eegSamples      MEMBER eegSamples)
    Q_PROPERTY(qint64  videoFrames     MEMBER videoFrames)
    Q_PROPERTY(int     markerCount     MEMBER markerCount)
    Q_PROPERTY(qint64  eegFileSizeBytes   MEMBER eegFileSizeBytes)
    Q_PROPERTY(qint64  videoFileSizeBytes MEMBER videoFileSizeBytes)
    Q_PROPERTY(QString startTime       MEMBER startTime)
    Q_PROPERTY(QString endTime         MEMBER endTime)

public:
    QString sessionName;
    QString savePath;
    double  durationSeconds   = 0.0;
    qint64  eegSamples        = 0;    // Total rows written to the EEG CSV
    qint64  videoFrames       = 0;    // Total frames written to the frames CSV
    int     markerCount       = 0;    // Total rows written to the markers CSV
    qint64  eegFileSizeBytes  = 0;
    qint64  videoFileSizeBytes = 0;
    QString startTime;                // ISO 8601 wall-clock start time
    QString endTime;                  // ISO 8601 wall-clock end time

    // -----------------------------------------------------------------------
    // Human-readable formatters — used by the QML summary dialog
    // -----------------------------------------------------------------------

    /* Formats durationSeconds as HH:MM:SS */
    QString durationFormatted() const {
        int totalSec = static_cast<int>(durationSeconds);
        int h = totalSec / 3600;
        int m = (totalSec % 3600) / 60;
        int s = totalSec % 60;
        return QString("%1:%2:%3")
            .arg(h, 2, 10, QChar('0'))
            .arg(m, 2, 10, QChar('0'))
            .arg(s, 2, 10, QChar('0'));
    }

    QString eegSizeFormatted()   const { return formatBytes(eegFileSizeBytes);   }
    QString videoSizeFormatted() const { return formatBytes(videoFileSizeBytes); }

private:
    /* Auto-scales bytes to the most readable SI unit (B → KB → MB → GB) */
    static QString formatBytes(qint64 bytes) {
        if (bytes < 1024)
            return QString::number(bytes) + " B";
        if (bytes < 1024 * 1024)
            return QString::number(bytes / 1024.0, 'f', 1) + " KB";
        if (bytes < 1024LL * 1024 * 1024)
            return QString::number(bytes / (1024.0 * 1024.0), 'f', 1) + " MB";
        return QString::number(bytes / (1024.0 * 1024.0 * 1024.0), 'f', 2) + " GB";
    }
};

Q_DECLARE_METATYPE(RecordingSummary)

#endif // RECORDINGSUMMARY_H
