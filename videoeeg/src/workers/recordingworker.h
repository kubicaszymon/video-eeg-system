/*
 * ==========================================================================
 *  recordingworker.h — Background Thread Disk I/O Worker
 * ==========================================================================
 *
 *  PURPOSE:
 *    Performs all file system operations for a recording session on a
 *    dedicated QThread. This offloads every disk write from the main thread,
 *    ensuring EEG display updates and UI responsiveness are unaffected
 *    even during 24-hour recordings with high-frequency flushes.
 *
 *  DESIGN PATTERN:
 *    Worker-Thread (QObject + moveToThread). RecordingWorker is created on
 *    the main thread then moved: worker->moveToThread(m_workerThread).
 *    All public slots execute on m_workerThread's event loop.
 *    Communication is strictly signal-driven:
 *      Main thread → worker:  emit requestXxx() signals (QueuedConnection)
 *      Worker → main thread:  emit filesInitialized() / batchWritten() / etc.
 *
 *  FILES MANAGED (per session):
 *    1. EEG CSV     — LSL_Timestamp + channel values per sample.
 *       Special:      PAUSE_START / PAUSE_STOP in-band marker rows.
 *       Precision:    6 dp timestamps (μs); 4 dp amplitudes (0.1 μV).
 *    2. Markers CSV — Type, Label, LSL_Timestamp, SessionTimeSec.
 *       Flushed immediately: markers are clinically critical annotations.
 *    3. Frames CSV  — FrameNumber, LSL_Timestamp, SegmentFile.
 *       Flushed every 100 frames (avoids 30 fsync/sec at 30 fps).
 *    4. Metadata JSON — Written once at session open time.
 *
 *  BATCHING RATIONALE:
 *    RecordingManager accumulates EEG_BATCH_SIZE (100) samples before
 *    invoking writeEegBatch(), reducing writes to ~2-3 per second.
 *    A 5-second watchdog timer in RecordingManager ensures that data is
 *    never held in the batch for more than 5 seconds.
 *
 *  FLUSH POLICY:
 *    QTextStream::flush() + QFile::flush() are called after every write.
 *    QTextStream flushes to the OS buffer; QFile::flush() calls fsync,
 *    ensuring data survives power loss. The double flush is intentional.
 *
 * ==========================================================================
 */

#ifndef RECORDINGWORKER_H
#define RECORDINGWORKER_H

#include <QObject>
#include <QFile>
#include <QTextStream>
#include <QVector>
#include <QStringList>
#include <QJsonObject>
#include "recordingsummary.h"

class RecordingWorker : public QObject
{
    Q_OBJECT

public:
    explicit RecordingWorker(QObject* parent = nullptr);
    ~RecordingWorker();

public slots:
    /* Opens all output files and writes CSV/JSON headers.
     * Must be the first slot invoked after the worker thread starts.
     * Emits filesInitialized(true) on success; filesInitialized(false, error)
     * on failure, leaving all previously opened files cleanly closed. */
    void initializeFiles(const QString& eegPath,
                         const QString& markersPath,
                         const QString& framesPath,
                         const QString& metadataPath,
                         const QStringList& channelNames,
                         const QString& sessionName,
                         double samplingRate);

    /* Writes a batch of EEG samples to the EEG CSV and flushes to disk.
     * @param samples     [sampleIdx][channelIdx], selected channels only
     * @param timestamps  LSL timestamp per sample row */
    void writeEegBatch(const QVector<QVector<float>>& samples,
                       const QVector<double>& timestamps);

    /* Writes PAUSE_START or PAUSE_STOP to both the EEG CSV (in-band) and
     * the markers CSV so analysis software can detect boundaries in either file. */
    void writePauseMarker(const QString& type, double lslTimestamp, double sessionTimeSec);

    /* Writes a single clinical event marker. Flushed immediately to disk
     * because markers are safety-critical annotations (e.g. seizure onset). */
    void writeMarker(const QString& type, const QString& label,
                     double lslTimestamp, double sessionTimeSec);

    /* Appends a frame entry to the frames CSV.
     * @param segmentFile  MKV basename for this frame (changes on pause/resume) */
    void writeFrameTimestamp(double lslTimestamp, qint64 frameNumber,
                             const QString& segmentFile);

    /* Flushes and closes all files, builds RecordingSummary, emits filesClosed().
     * @param videoFileSizeBytes  Summed size of all MKV segments (from main thread) */
    void closeFiles(double durationSeconds, qint64 videoFileSizeBytes);

    // -----------------------------------------------------------------
    // Session state persistence (crash recovery / Auto-Resume)
    // -----------------------------------------------------------------

    /* Atomically writes the current session state to disk. Called periodically
     * (every 5 s, piggy-backed on the flush timer) so the file is always
     * reasonably up-to-date. Uses write-to-tmp-then-rename for atomicity. */
    void writeSessionState(const QJsonObject& stateJson, const QString& statePath);

    /* Marks the session as cleanly closed in the session state file.
     * Called as the final operation of closeFiles(). */
    void markSessionClosed(const QString& statePath);

signals:
    void filesInitialized(bool success, const QString& error);
    void batchWritten(int sampleCount, qint64 eegFileSize);
    void filesClosed(const RecordingSummary& summary);
    void errorOccurred(const QString& error);

private:
    void writeEegHeader(const QStringList& channelNames,
                        const QString& sessionName,
                        double samplingRate);
    void writeMarkersHeader();
    void writeFramesHeader();
    void writeMetadata(const QString& sessionName,
                       const QStringList& channelNames,
                       double samplingRate);

    // -----------------------------------------------------------------
    // Atomic JSON write helper — writes to a .tmp file then renames to
    // the final path in a single operation. On NTFS (Windows) and most
    // POSIX filesystems, rename() is atomic, so the target file is
    // never left in a half-written state on power loss.
    // -----------------------------------------------------------------
    static bool atomicWriteJson(const QString& finalPath, const QJsonObject& json);

    QFile m_eegFile;
    QFile m_markersFile;
    QFile m_framesFile;
    QTextStream m_eegStream;
    QTextStream m_markersStream;
    QTextStream m_framesStream;

    QString m_sessionName;
    QString m_savePath;
    qint64 m_sampleCount = 0;
    qint64 m_markerCount = 0;
    qint64 m_frameCount = 0;
};

#endif // RECORDINGWORKER_H
