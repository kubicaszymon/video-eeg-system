/*
 * ==========================================================================
 *  markermanager.cpp — Event Marker Management Implementation
 * ==========================================================================
 *  See markermanager.h for architecture overview and marker lifecycle.
 * ==========================================================================
 */

#include "markermanager.h"
#include <QDebug>

MarkerManager::MarkerManager(QObject *parent)
    : QObject{parent}
{
    qInfo() << "[MarkerManager] Created";
}

// ============================================================================
// Type Configuration Registry
// ============================================================================

const QMap<QString, QPair<QString, QColor>>& MarkerManager::markerTypeConfig()
{
    /* Color choices follow clinical EEG conventions:
     *   Blue/Purple  — physiological state changes (eyes)
     *   Red/Green    — pathological events (seizure onset/offset)
     *   Orange       — artifacts
     *   Gray         — user-defined custom markers */
    static const QMap<QString, QPair<QString, QColor>> config = {
        {"eyes_open",     {"Eyes Open",     QColor("#3498db")}},
        {"eyes_closed",   {"Eyes Closed",   QColor("#9b59b6")}},
        {"seizure_start", {"Seizure Start", QColor("#e74c3c")}},
        {"seizure_stop",  {"Seizure Stop",  QColor("#27ae60")}},
        {"artifact",      {"Artifact",      QColor("#f39c12")}},
        {"custom",        {"Custom",        QColor("#95a5a6")}}
    };
    return config;
}

QString MarkerManager::getLabelForType(const QString& type)
{
    const auto& config = markerTypeConfig();
    if (config.contains(type)) {
        return config[type].first;
    }
    return type;
}

QColor MarkerManager::getColorForType(const QString& type)
{
    const auto& config = markerTypeConfig();
    if (config.contains(type)) {
        return config[type].second;
    }
    return QColor("#95a5a6");
}

// ============================================================================
// Marker CRUD Operations
// ============================================================================

void MarkerManager::addMarkerAtPosition(const QString& type, double xPosition, double absoluteTime, const QString& customLabel)
{
    Marker marker;
    marker.type = type;
    marker.xPosition = xPosition;
    marker.absoluteTime = absoluteTime;
    marker.color = getColorForType(type);

    if (!customLabel.isEmpty()) {
        marker.label = customLabel;
    } else {
        marker.label = getLabelForType(type);
    }

    m_markers.append(marker);

    qInfo() << "[MarkerManager] Added marker:" << marker.label
            << "at X:" << marker.xPosition
            << "absoluteTime:" << marker.absoluteTime;

    emit markerAdded(marker.type, marker.xPosition, marker.label, marker.color);
    emit markersChanged();
}

void MarkerManager::removeMarker(int index)
{
    if (index >= 0 && index < m_markers.size()) {
        qInfo() << "[MarkerManager] Removing marker:" << m_markers[index].label;
        m_markers.removeAt(index);
        emit markersChanged();
    }
}

void MarkerManager::removeMarkersInRange(double startX, double endX, double timeWindowSeconds)
{
    /*
     * Called after each circular buffer write to garbage-collect markers
     * that the new data has overwritten. Two cases:
     *
     * Normal (startX <= endX):
     *   Remove markers where startX <= markerX <= endX.
     *
     * Wraparound (startX > endX):
     *   The write crossed the buffer boundary. Remove markers where
     *   markerX >= startX (end of buffer) OR markerX <= endX (start of buffer).
     *   Example: startX=9.5, endX=0.5 means range [9.5..10.0] + [0.0..0.5].
     *
     * Iterates in reverse to safely remove elements during traversal.
     */
    bool removed = false;

    for (int i = m_markers.size() - 1; i >= 0; --i) {
        double markerX = m_markers[i].xPosition;

        bool shouldRemove = false;

        if (startX <= endX) {
            shouldRemove = (markerX >= startX && markerX <= endX);
        } else {
            shouldRemove = (markerX >= startX || markerX <= endX);
        }

        if (shouldRemove) {
            qInfo() << "[MarkerManager] Removing overwritten marker:" << m_markers[i].label
                    << "at X:" << markerX;
            m_markers.removeAt(i);
            removed = true;
        }
    }

    if (removed) {
        emit markersChanged();
    }
}

void MarkerManager::clearMarkers()
{
    qInfo() << "[MarkerManager] Clearing all" << m_markers.size() << "markers";
    m_markers.clear();
    emit markersChanged();
}

// ============================================================================
// QML Data Bridge
// ============================================================================

QVariantList MarkerManager::markersAsVariant() const
{
    /* Convert to QVariantList<QVariantMap> for QML consumption.
     * QML cannot directly iterate Q_GADGET lists, so this manual
     * conversion is necessary for the markers property binding. */
    QVariantList result;

    for (const auto& marker : m_markers) {
        QVariantMap markerMap;
        markerMap["type"] = marker.type;
        markerMap["label"] = marker.label;
        markerMap["xPosition"] = marker.xPosition;
        markerMap["absoluteTime"] = marker.absoluteTime;
        markerMap["color"] = marker.color;
        result.append(markerMap);
    }

    return result;
}
