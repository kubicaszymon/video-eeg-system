/*
 * ==========================================================================
 *  markermanager.h — EEG Event Marker Management
 * ==========================================================================
 *
 *  PURPOSE:
 *    Stores and manages user-placed event markers on the EEG waveform.
 *    Markers represent clinically significant moments (eyes open/closed,
 *    seizure onset/offset, artifacts) and are displayed as vertical lines
 *    on the EegGraph.qml waveform with color-coded labels.
 *
 *  DESIGN PATTERN:
 *    Owned component — created and owned by EegBackend, exposed to QML
 *    via the markerManager property. Not a singleton; each EegBackend
 *    instance has its own MarkerManager.
 *
 *  MARKER LIFECYCLE ON THE CIRCULAR BUFFER:
 *    Markers are placed at fixed X positions (time in seconds within the
 *    display window). When the circular buffer's write cursor sweeps past
 *    a marker's X position, that marker is automatically removed by
 *    removeMarkersInRange() — called from EegBackend::updateMarkersAfterWrite().
 *
 *    This ensures markers disappear as the old data they annotate is
 *    overwritten, keeping the display consistent.
 *
 *  DUAL COORDINATE SYSTEM:
 *    xPosition    — relative position in the display window (0 to timeWindowSeconds),
 *                   used for rendering on the graph.
 *    absoluteTime — LSL timestamp (lsl::local_clock()), used for recording/export.
 *                   This allows markers to be correlated with EEG data in CSV files.
 *
 *  DATA FLOW:
 *    User clicks marker button in QML
 *      → EegBackend::addMarker(type)
 *        → MarkerManager::addMarkerAtPosition()  [display marker]
 *        → RecordingManager::writeMarker()        [persistent record]
 *
 *  SUPPORTED MARKER TYPES:
 *    eyes_open, eyes_closed, seizure_start, seizure_stop, artifact, custom
 *    Each type has a predefined label and color defined in markerTypeConfig().
 *
 * ==========================================================================
 */

#ifndef MARKERMANAGER_H
#define MARKERMANAGER_H

#include <QObject>
#include <QList>
#include <QString>
#include <QColor>
#include <QVariantList>
#include <QtQml/qqmlregistration.h>

/* Value type representing a single event marker on the EEG display.
 * Q_GADGET enables property access from QML via QVariantMap conversion. */
struct Marker {
    Q_GADGET
    Q_PROPERTY(QString type MEMBER type)
    Q_PROPERTY(QString label MEMBER label)
    Q_PROPERTY(double xPosition MEMBER xPosition)
    Q_PROPERTY(double absoluteTime MEMBER absoluteTime)
    Q_PROPERTY(QColor color MEMBER color)

public:
    QString type;
    QString label;
    double xPosition;       // X position in seconds within the display window
    double absoluteTime;    // LSL timestamp for recording correlation
    QColor color;
};

Q_DECLARE_METATYPE(Marker)

class MarkerManager : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QVariantList markers READ markersAsVariant NOTIFY markersChanged FINAL)
    Q_PROPERTY(int markerCount READ markerCount NOTIFY markersChanged FINAL)

public:
    explicit MarkerManager(QObject *parent = nullptr);

    /* Creates a new marker and appends it to the internal list.
     * @param type          Marker type key (e.g. "eyes_open", "seizure_start")
     * @param xPosition     Time coordinate in seconds within the display window
     * @param absoluteTime  LSL timestamp for recording export correlation
     * @param customLabel   If non-empty, overrides the default label for the type
     * Emits markerAdded() and markersChanged() after insertion. */
    Q_INVOKABLE void addMarkerAtPosition(const QString& type, double xPosition, double absoluteTime, const QString& customLabel = "");

    /* Removes a single marker by its position in the internal list.
     * Used by QML for user-initiated marker deletion. Safe for out-of-range indices. */
    Q_INVOKABLE void removeMarker(int index);

    /* Garbage-collects markers that fall within the overwritten data range.
     * Called by EegBackend::updateMarkersAfterWrite() after each circular buffer write.
     * Handles two cases:
     *   Normal (startX <= endX): removes markers in [startX, endX]
     *   Wraparound (startX > endX): removes markers in [startX, end] + [0, endX] */
    void removeMarkersInRange(double startX, double endX, double timeWindowSeconds);

    /* Removes all markers. Called when the time window changes (marker positions
     * become invalid) or when the user explicitly clears the session. */
    Q_INVOKABLE void clearMarkers();

    /* Converts the internal QList<Marker> to a QVariantList of QVariantMaps
     * for QML property binding. QML cannot directly iterate C++ QList<Q_GADGET>,
     * so this manual conversion bridges the gap. */
    QVariantList markersAsVariant() const;

    /* Returns the number of currently active markers. Bound to markerCount property. */
    int markerCount() const { return m_markers.size(); }

    /* Static lookups: resolve a marker type key to its human-readable label
     * or display color. Used by both MarkerManager (for creating markers)
     * and EegBackend (for recording export). */
    static QString getLabelForType(const QString& type);
    static QColor getColorForType(const QString& type);

signals:
    /* Emitted whenever the marker list changes (add, remove, clear).
     * Drives the QML markers property binding refresh. */
    void markersChanged();

    /* Emitted after a single marker is added. Provides the marker details
     * for immediate UI feedback (e.g. animation, toast notification). */
    void markerAdded(const QString& type, double xPosition, const QString& label, const QColor& color);

private:
    QList<Marker> m_markers;

    /* Static registry of marker types → (label, color) pairs.
     * Uses Meyer's singleton pattern for thread-safe lazy initialization. */
    static const QMap<QString, QPair<QString, QColor>>& markerTypeConfig();
};

#endif // MARKERMANAGER_H
