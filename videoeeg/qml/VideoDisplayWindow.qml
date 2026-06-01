import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtQuick.Layouts
import QtMultimedia
import videoEeg

/**
 * VideoDisplayWindow - Video display window with real-time EEG synchronization
 *
 * This window displays the live camera feed alongside EEG synchronization data,
 * providing the operator with real-time feedback on alignment quality between
 * the two independent data streams (video and EEG).
 *
 * SYNCHRONIZATION ARCHITECTURE:
 *   Both streams are timestamped using lsl::local_clock() at capture time:
 *     - EEG: timestamps from LSL pull_chunk() (hardware amplifier clock,
 *            corrected for drift via time_correction())
 *     - Video: lsl::local_clock() called in CameraManager::onVideoFrameChanged()
 *
 *   On each frame arrival, this window queries EegSyncManager.getEEGForFrame()
 *   with the frame's LSL timestamp to retrieve the matching EEG data and
 *   display the synchronization offset (ideally < 5 ms for clinical use).
 *
 * OVERLAY PANELS:
 *   - Top-right:  LSL timestamp + EEG sync offset for the current frame
 *   - Bottom-left: EEG sync health dashboard (status, drift, buffer state)
 *
 * DATA FLOW (per frame):
 *   CameraManager::frameReady(packet)
 *     -> VideoBackend::onFrameReady()
 *       -> emit frameReceived(lslTimestamp)
 *         -> [QML] onFrameReceived handler
 *           -> EegSyncManager.getEEGForFrame(lslTimestamp)
 *             -> updates overlay labels with sync offset, channel values, health
 *
 * Features:
 * - Real-time video display via Qt Multimedia
 * - Per-frame EEG synchronization with offset display
 * - Sync health dashboard (SYNCED / WARNING / DESYNC)
 * - Clock drift and time correction monitoring
 * - Out-of-range detection when buffers don't overlap
 * - Frame buffer and EEG buffer status comparison
 */
ApplicationWindow {
    id: videoWindow
    width: 900
    height: 700
    minimumWidth: 500
    minimumHeight: 400
    title: "Video Recording - " + (backend.cameraName || "No Camera")
    visible: true

    property string cameraId: ""

    // --- EEG sync state (updated on each frame via getEEGForFrame) ---
    property bool   eegSyncValid: false
    property double eegSyncOffsetMs: 0.0
    property bool   eegSyncOutOfRange: false
    property double eegSyncRangeErrorMs: 0.0
    property int    eegSyncChannelCount: 0

    readonly property color bgColor: "#0e1419"
    readonly property color panelColor: "#1a2332"
    readonly property color accentColor: "#4a90e2"
    readonly property color successColor: "#2ecc71"
    readonly property color warningColor: "#f39c12"
    readonly property color dangerColor: "#c0392b"
    readonly property color textColor: "#e8eef5"
    readonly property color textSecondary: "#8a9cb5"

    /**
     * Resolves the sync health status string to a display color.
     * Mirrors the thresholds in EegSyncManager::healthStatus():
     *   SYNCED  (< 5 ms)  -> green  — acceptable for clinical event marking
     *   WARNING (5-15 ms) -> yellow — drift accumulating
     *   DESYNC  (> 15 ms) -> red    — synchronization unreliable
     */
    function syncStatusColor(status) {
        if (status === "SYNCED")  return successColor
        if (status === "WARNING") return warningColor
        return dangerColor
    }

    VideoBackend {
        id: backend
        cameraId: videoWindow.cameraId
        videoSink: videoOutput.videoSink

        onErrorOccurred: function(error) {
            console.error("Video error:", error)
            errorLabel.text = error
            errorLabel.visible = true
        }

        /**
         * SYNCHRONIZATION HOT PATH (QML side)
         *
         * Called on every frame arrival (~30 Hz). Queries EegSyncManager
         * for the EEG data matching this frame's LSL timestamp and updates
         * the overlay properties. The query is O(log N) in the EEG buffer
         * size, which is negligible at 30 Hz.
         *
         * The result map contains:
         *   valid       - bool: whether matching EEG data was found
         *   outOfRange  - bool: timestamp outside EEG buffer range
         *   rangeErrorMs- double: distance from buffer boundary (if out of range)
         *   offsetMs    - double: |videoTs - eegTs| in milliseconds
         *   channels    - list<double>: channel values in uV
         *   timestamp   - double: matched EEG sample's LSL timestamp
         */
        onFrameReceived: function(lslTimestamp) {
            var result = EegSyncManager.getEEGForFrame(lslTimestamp)

            videoWindow.eegSyncValid = result.valid || false
            videoWindow.eegSyncOffsetMs = result.offsetMs || 0.0
            videoWindow.eegSyncOutOfRange = result.outOfRange || false
            videoWindow.eegSyncRangeErrorMs = result.rangeErrorMs || 0.0

            if (result.valid && result.channels) {
                videoWindow.eegSyncChannelCount = result.channels.length
            }
        }
    }

    Component.onCompleted: {
        console.log("VideoDisplayWindow opened with camera ID:", cameraId)
        if (cameraId !== "") {
            backend.startCapture()
        }
    }

    Component.onDestruction: {
        backend.stopCapture()
    }

    Rectangle {
        anchors.fill: parent
        color: bgColor

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // TOP TOOLBAR
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 50
                color: panelColor

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 15
                    spacing: 15

                    Label {
                        text: "Video"
                        font.pixelSize: 16
                        font.bold: true
                        color: textColor
                    }

                    ColumnLayout {
                        spacing: 0

                        Label {
                            text: backend.cameraName || "No Camera"
                            font.pixelSize: 12
                            color: textSecondary
                        }

                        Label {
                            text: "LSL Synchronized"
                            font.pixelSize: 10
                            color: textSecondary
                        }
                    }

                    Item { Layout.fillWidth: true }

                    // EEG Sync status badge - quick glance at synchronization health
                    Rectangle {
                        Layout.preferredWidth: syncBadgeRow.width + 16
                        Layout.preferredHeight: 28
                        color: syncStatusColor(EegSyncManager.healthStatus)
                        radius: 4
                        opacity: 0.9
                        visible: backend.isCapturing

                        RowLayout {
                            id: syncBadgeRow
                            anchors.centerIn: parent
                            spacing: 6

                            Rectangle {
                                width: 8
                                height: 8
                                radius: 4
                                color: "white"
                            }

                            Label {
                                text: "EEG " + EegSyncManager.healthStatus
                                font.pixelSize: 10
                                font.bold: true
                                color: "white"
                            }
                        }
                    }

                    // Recording indicator
                    Rectangle {
                        Layout.preferredWidth: 120
                        Layout.preferredHeight: 35
                        color: backend.isCapturing ? dangerColor : "#2d3e50"
                        radius: 4

                        RowLayout {
                            anchors.centerIn: parent
                            spacing: 8

                            Rectangle {
                                width: 10
                                height: 10
                                radius: 5
                                color: "white"
                                visible: backend.isCapturing

                                SequentialAnimation on opacity {
                                    running: backend.isCapturing
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.3; duration: 500 }
                                    NumberAnimation { from: 0.3; to: 1; duration: 500 }
                                }
                            }

                            Label {
                                text: backend.isCapturing ? "CAPTURING" : "STOPPED"
                                font.pixelSize: 11
                                font.bold: true
                                color: "white"
                            }
                        }
                    }

                    // Control buttons
                    Button {
                        text: backend.isCapturing ? "Stop" : "Start"
                        font.pixelSize: 11
                        Layout.preferredHeight: 35
                        palette.button: backend.isCapturing ? dangerColor : successColor
                        palette.buttonText: "white"

                        onClicked: {
                            if (backend.isCapturing) {
                                backend.stopCapture()
                            } else {
                                backend.startCapture()
                            }
                        }
                    }
                }
            }

            // VIDEO DISPLAY AREA
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                VideoOutput {
                    id: videoOutput
                    anchors.fill: parent
                    anchors.margins: 10
                    fillMode: VideoOutput.PreserveAspectFit

                    // --- TOP-RIGHT OVERLAY: Frame timestamp + EEG sync offset ---
                    Rectangle {
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 10
                        width: timestampColumn.width + 20
                        height: timestampColumn.height + 16
                        color: "#cc000000"
                        radius: 6
                        visible: backend.isCapturing

                        Column {
                            id: timestampColumn
                            anchors.centerIn: parent
                            spacing: 4

                            Label {
                                text: "LSL Time"
                                font.pixelSize: 9
                                color: textSecondary
                            }

                            Label {
                                text: backend.lastFrameTimestamp.toFixed(6)
                                font.pixelSize: 12
                                font.family: "monospace"
                                font.bold: true
                                color: accentColor
                            }

                            // EEG sync offset for the current frame
                            Label {
                                text: eegSyncValid
                                      ? "EEG offset: " + eegSyncOffsetMs.toFixed(2) + " ms"
                                      : (eegSyncOutOfRange
                                         ? "EEG out of range (" + eegSyncRangeErrorMs.toFixed(0) + " ms)"
                                         : "EEG: no data")
                                font.pixelSize: 10
                                font.family: "monospace"
                                color: eegSyncValid
                                       ? (eegSyncOffsetMs < 5 ? successColor : (eegSyncOffsetMs < 15 ? warningColor : dangerColor))
                                       : dangerColor
                            }
                        }
                    }

                    // --- BOTTOM-LEFT OVERLAY: EEG Sync Health Dashboard ---
                    Rectangle {
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.margins: 10
                        width: syncDashColumn.width + 24
                        height: syncDashColumn.height + 16
                        color: "#cc000000"
                        radius: 6
                        visible: backend.isCapturing

                        Column {
                            id: syncDashColumn
                            anchors.centerIn: parent
                            spacing: 3

                            Label {
                                text: "EEG-Video Sync"
                                font.pixelSize: 10
                                font.bold: true
                                color: textColor
                            }

                            // Health status with color indicator
                            Row {
                                spacing: 6
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: syncStatusColor(EegSyncManager.healthStatus)
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Label {
                                    text: EegSyncManager.healthStatus
                                    font.pixelSize: 10
                                    font.bold: true
                                    font.family: "monospace"
                                    color: syncStatusColor(EegSyncManager.healthStatus)
                                }
                            }

                            // Average sync offset
                            Label {
                                text: "Avg offset: " + EegSyncManager.avgSyncOffsetMs.toFixed(2) + " ms"
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: textSecondary
                            }

                            // Clock drift correction
                            Label {
                                text: "Drift corr: " + EegSyncManager.timeCorrectionMs.toFixed(3) + " ms"
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: textSecondary
                            }

                            // Clock drift rate
                            Label {
                                text: "Drift rate: " + EegSyncManager.clockDriftMs.toFixed(3) + " ms/10s"
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: Math.abs(EegSyncManager.clockDriftMs) < 1.0 ? textSecondary : warningColor
                            }

                            // EEG buffer status
                            Label {
                                text: "EEG buf: " + EegSyncManager.bufferSize + "/" + EegSyncManager.maxBufferSize
                                      + " (" + EegSyncManager.bufferDurationSec.toFixed(1) + "s)"
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: textSecondary
                            }

                            // Channels matched
                            Label {
                                text: "Channels: " + eegSyncChannelCount
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: textSecondary
                                visible: eegSyncChannelCount > 0
                            }

                            // Out-of-range warning (only when there are issues)
                            Label {
                                text: "Out-of-range queries: " + EegSyncManager.outOfRangeCount
                                      + "/" + EegSyncManager.totalQueryCount
                                font.pixelSize: 9
                                font.family: "monospace"
                                color: dangerColor
                                visible: EegSyncManager.outOfRangeCount > 0
                            }
                        }
                    }
                }

                // Placeholder when not capturing
                Column {
                    anchors.centerIn: parent
                    spacing: 15
                    visible: !backend.isCapturing

                    Label {
                        text: "Video"
                        font.pixelSize: 48
                        font.bold: true
                        color: "#3d4f5f"
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Label {
                        text: "Press 'Start' to begin video capture"
                        font.pixelSize: 14
                        color: textSecondary
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Label {
                        text: "Frames will be timestamped with LSL clock"
                        font.pixelSize: 11
                        color: "#7f8c8d"
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }

                // Error display
                Rectangle {
                    id: errorLabel
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 10
                    height: 40
                    color: "#cc990000"
                    radius: 4
                    visible: false

                    property alias text: errorText.text

                    Label {
                        id: errorText
                        anchors.centerIn: parent
                        font.pixelSize: 12
                        color: "white"
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: errorLabel.visible = false
                    }
                }
            }

            // BOTTOM STATUS BAR
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 35
                color: panelColor

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 15
                    spacing: 20

                    // FPS
                    Label {
                        text: "FPS: " + backend.currentFps.toFixed(1)
                        font.pixelSize: 10
                        color: backend.currentFps > 20 ? successColor : (backend.currentFps > 10 ? warningColor : dangerColor)
                    }

                    Rectangle {
                        width: 1
                        height: 20
                        color: "#2d3e50"
                    }

                    // Frame count
                    Label {
                        text: "Frames: " + backend.frameCount
                        font.pixelSize: 10
                        color: textSecondary
                    }

                    Rectangle {
                        width: 1
                        height: 20
                        color: "#2d3e50"
                    }

                    // Video buffer status
                    Label {
                        text: "VBuf: " + backend.bufferSize + "/" + backend.maxBufferSize
                        font.pixelSize: 10
                        color: textSecondary
                    }

                    Rectangle {
                        width: 1
                        height: 20
                        color: "#2d3e50"
                    }

                    // EEG sync offset (quick-glance metric)
                    Label {
                        text: "Sync: " + (eegSyncValid ? eegSyncOffsetMs.toFixed(1) + "ms" : "N/A")
                        font.pixelSize: 10
                        color: eegSyncValid
                               ? (eegSyncOffsetMs < 5 ? successColor : (eegSyncOffsetMs < 15 ? warningColor : dangerColor))
                               : textSecondary
                    }

                    Rectangle {
                        width: 1
                        height: 20
                        color: "#2d3e50"
                    }

                    // Latest timestamp
                    Label {
                        text: "LSL: " + (backend.lastFrameTimestamp > 0 ?
                              backend.lastFrameTimestamp.toFixed(3) + "s" : "N/A")
                        font.pixelSize: 10
                        color: accentColor
                    }

                    Item { Layout.fillWidth: true }

                    // Connection status
                    Rectangle {
                        width: 10
                        height: 10
                        radius: 5
                        color: backend.isConnected ? successColor : dangerColor
                    }

                    Label {
                        text: backend.isConnected ? "Connected" : "Disconnected"
                        font.pixelSize: 10
                        color: backend.isConnected ? successColor : dangerColor
                    }
                }
            }
        }
    }
}
