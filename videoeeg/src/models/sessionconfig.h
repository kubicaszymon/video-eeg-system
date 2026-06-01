/*
 * ==========================================================================
 *  sessionconfig.h — Recording Session Configuration
 * ==========================================================================
 *
 *  PURPOSE:
 *    Plain-data container holding everything required to start a recording
 *    session. Constructed in AmplifierSetupBackend (from the user's choices
 *    in the settings window) and passed as a JS object through QML to
 *    RecordingManager::startRecording().
 *
 *  DESIGN PATTERN:
 *    Value Object — no identity, no signals, copied freely. Deliberately
 *    kept as a plain C++ struct (not Q_GADGET) since it is never exposed
 *    to QML directly; it is always decomposed into individual parameters
 *    at the call site.
 *
 *  FILE NAMING CONVENTION:
 *    All output files share the sessionName prefix and live in saveFolderPath.
 *    Naming scheme (auto-generated: "REC_YYYYMMDD_HHMMSS"):
 *
 *      <sessionName>_eeg.csv          — EEG samples, LSL timestamps, μV
 *      <sessionName>_markers.csv      — Event markers with LSL timestamps
 *      <sessionName>_frames.csv       — Video frame index (frame# → LSL ts)
 *      <sessionName>_metadata.json    — Session metadata (rate, channels, etc.)
 *      <sessionName>_video.mkv        — Video segment 1 (H.264/MKV)
 *      <sessionName>_video_seg002.mkv — Video segment 2 (after pause/resume)
 *      <sessionName>_video_seg003.mkv — etc.
 *
 *  VIDEO SEGMENTATION:
 *    Each pause/resume cycle starts a new video segment file (seg002, seg003).
 *    The frames CSV records which segment each frame belongs to, so post-hoc
 *    software can reassemble the full video-EEG timeline.
 *
 * ==========================================================================
 */

#ifndef SESSIONCONFIG_H
#define SESSIONCONFIG_H

#include <QString>
#include <QStringList>
#include <QVector>
#include <QDir>

struct SessionConfig
{
    QString     saveFolderPath; // Absolute path to the output folder chosen by the user
    QString     sessionName;    // Auto-generated identifier: "REC_YYYYMMDD_HHMMSS"
    QString     amplifierId;    // Platform device ID passed to AmplifierManager::startStream()
    QVector<int> channels;      // Selected channel indices (hardware → display mapping)
    QStringList channelNames;   // Resolved human-readable labels (e.g. "Fp1", "C3")
    QString     cameraId;       // Platform camera device ID (empty = no video recording)
    double      samplingRate = 0.0;

    // -----------------------------------------------------------------------
    // File path helpers — all paths computed from saveFolderPath + sessionName
    // -----------------------------------------------------------------------

    /* EEG data file: timestamp + channel values, one row per sample */
    QString eegFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_eeg.csv");
    }

    /* Primary video file (segment 1, or only segment if no pause/resume) */
    QString videoFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_video.mkv");
    }

    /* Video segment file for a given segment number.
     * Segment 1 returns videoFilePath() (no suffix).
     * Segments ≥ 2 get a zero-padded suffix: _seg002, _seg003, etc.
     * The suffix width of 3 supports up to 999 pause/resume cycles. */
    QString videoSegmentFilePath(int segment) const {
        if (segment <= 1)
            return videoFilePath();
        return QDir(saveFolderPath).filePath(
            sessionName + QString("_video_seg%1.mkv").arg(segment, 3, 10, QChar('0')));
    }

    /* Event markers file: type, label, LSL timestamp, session-relative time */
    QString markersFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_markers.csv");
    }

    /* Video frame index: frame number, LSL timestamp, segment filename */
    QString framesFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_frames.csv");
    }

    /* JSON metadata: sampling rate, channel names, start time, format info */
    QString metadataFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_metadata.json");
    }

    /* Persistent session state file for crash recovery (Auto-Resume).
     * Written periodically during recording. If the app crashes, this file's
     * "status" field will remain "recording" rather than "closed", allowing
     * the next launch to detect the unfinished session and offer to resume. */
    QString sessionStateFilePath() const {
        return QDir(saveFolderPath).filePath(sessionName + "_session_state.json");
    }

    /* Returns true if the minimum required fields are set.
     * Used by RecordingManager to validate before committing to disk I/O. */
    bool isValid() const {
        return !saveFolderPath.isEmpty() &&
               !sessionName.isEmpty() &&
               !channels.isEmpty();
    }
};

#endif // SESSIONCONFIG_H
