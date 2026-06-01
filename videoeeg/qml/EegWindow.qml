import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtQuick.Layouts
import QtMultimedia
import videoEeg

// EegWindow - Main EEG recording window (separate ApplicationWindow)
ApplicationWindow {
    id: eegWindow
    width: 1920
    height: 1080
    title: "EEG Recording System"
    visible: true
    visibility: Window.Maximized

    // Signal emitted when examination ends (to return to main menu)
    signal examinationEnded()

    property string amplifierId: ""
    property var channels: []
    property int channelCount: channels.length
    property string cameraId: ""

    // Session config passed from AmplifierSetupWindow
    property string saveFolderPath: ""
    property string sessionName: ""
    property var channelNamesList: []

    property bool isRecording: RecordingManager.isRecording
    property bool isPaused: RecordingManager.isPaused
    property int recordingTime: 0
    property string currentPatientName: "Jan Kowalski"

    readonly property color bgColor: "#0e1419"
    readonly property color panelColor: "#1a2332"
    readonly property color accentColor: "#4a90e2"
    readonly property color successColor: "#2ecc71"
    readonly property color warningColor: "#f39c12"
    readonly property color dangerColor: "#c0392b"
    readonly property color textColor: "#e8eef5"
    readonly property color textSecondary: "#8a9cb5"

    EegBackend {
        id: backend
        amplifierId: eegWindow.amplifierId
        channels: eegWindow.channels
        spacing: eegGraph.dynamicChannelSpacing
        timeWindowSeconds: timeSlider.value

        onChannelsChanged: {
            eegGraph.selectedChannels = channels
        }

        onSamplingRateChanged: { /* sampling rate updated — no action needed */ }
    }

    Timer {
        id: recordingTimer
        interval: 1000
        running: isRecording && !isPaused
        repeat: true
        onTriggered: recordingTime++
    }

    Component.onCompleted: {
        // Screen.pixelDensity returns pixels per millimeter; convert to DPI
        backend.scaler.screenDpi = Screen.pixelDensity * 25.4
        backend.registerDataModel(eegGraph.dataModel)
        eegGraph.selectedChannels = channels
        backend.startStream()
    }

    function formatTime(seconds) {
        var h = Math.floor(seconds / 3600)
        var m = Math.floor((seconds % 3600) / 60)
        var s = seconds % 60
        return (h < 10 ? "0" : "") + h + ":" +
               (m < 10 ? "0" : "") + m + ":" +
               (s < 10 ? "0" : "") + s
    }

    function addMarker(type) {
        // Call backend immediately — lsl::local_clock() is captured as the
        // very first thing inside EegBackend::addMarker so timestamp accuracy
        // is not affected by any QML overhead after this point.
        backend.addMarker(type)
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
                Layout.preferredHeight: 70
                color: panelColor
                z: 10

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 15
                    spacing: 20

                    RowLayout {
                        spacing: 12

                        Label {
                            text: "📊"
                            font.pixelSize: 28
                        }

                        ColumnLayout {
                            spacing: 2

                            Label {
                                text: "EEG Recording System"
                                font.pixelSize: 16
                                font.bold: true
                                color: textColor
                            }

                            Label {
                                text: currentPatientName + " • " + channelCount + " channels"
                                font.pixelSize: 11
                                color: textSecondary
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        Layout.preferredWidth: 300
                        Layout.preferredHeight: 50
                        color: isRecording ? (isPaused ? warningColor : dangerColor) : "#2d3e50"
                        radius: 6
                        border.color: isRecording ? "white" : "#7f8c8d"
                        border.width: 2

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 12

                            Rectangle {
                                width: 16
                                height: 16
                                radius: 8
                                color: "white"
                                visible: isRecording && !isPaused

                                SequentialAnimation on opacity {
                                    running: isRecording && !isPaused
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.3; duration: 500 }
                                    NumberAnimation { from: 0.3; to: 1; duration: 500 }
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                Label {
                                    text: isRecording ? (isPaused ? "⏸ PAUSED" : "⏺ RECORDING") : "⏹ LIVE PREVIEW"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: "white"
                                }

                                Label {
                                    text: isRecording ? formatTime(recordingTime) : "Not saving data"
                                    font.pixelSize: 10
                                    color: "white"
                                }
                            }
                        }
                    }

                    Label {
                        text: Qt.formatDateTime(new Date(), "dd.MM.yyyy  hh:mm:ss")
                        font.pixelSize: 11
                        color: textSecondary

                        Timer {
                            interval: 1000
                            running: true
                            repeat: true
                            onTriggered: parent.text = Qt.formatDateTime(new Date(), "dd.MM.yyyy  hh:mm:ss")
                        }
                    }
                }
            }

            // DISK SPACE WARNING BANNER
            // Shown when disk space drops below 5 GB but recording continues.
            // The banner is persistent and non-dismissible to ensure visibility.
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 40 : 0
                visible: RecordingManager.diskSpaceWarning && isRecording
                color: "#f39c12"
                z: 5

                Behavior on Layout.preferredHeight {
                    NumberAnimation { duration: 200 }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 15
                    spacing: 10

                    Label {
                        text: "LOW DISK SPACE"
                        font.pixelSize: 12
                        font.bold: true
                        color: "#1a1a1a"
                    }

                    Label {
                        text: RecordingManager.diskSpaceMB + " MB remaining"
                        font.pixelSize: 11
                        color: "#2c2c2c"
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: {
                            var hours = RecordingManager.estimatedRemainingHours
                            if (hours < 0) return ""
                            if (hours < 1) return "~" + Math.round(hours * 60) + " min remaining"
                            return "~" + hours.toFixed(1) + " h remaining"
                        }
                        font.pixelSize: 11
                        font.bold: true
                        color: "#1a1a1a"
                    }
                }
            }

            // MAIN CONTENT
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                // LEFT PANEL
                Rectangle {
                    Layout.preferredWidth: 280
                    Layout.fillHeight: true
                    color: panelColor

                    ScrollView {
                        anchors.fill: parent
                        clip: true
                        contentWidth: availableWidth

                        Item {
                            width: 280
                            height: contentColumn.implicitHeight + 30

                            ColumnLayout {
                                id: contentColumn
                                anchors.fill: parent
                                anchors.topMargin: 15
                                anchors.leftMargin: 15
                                anchors.rightMargin: 15
                                anchors.bottomMargin: 15
                                spacing: 15

                                // RECORDING CONTROL
                                ControlSection {
                                    title: "⏺ Recording Control"
                                    textColor: eegWindow.textColor

                                    Button {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 45
                                        text: isRecording ? "⏹ Stop" : "⏺ Start Recording"
                                        font.pixelSize: 12
                                        font.bold: true
                                        palette.button: isRecording ? dangerColor : successColor
                                        palette.buttonText: "white"

                                        onClicked: {
                                            if (isRecording) {
                                                RecordingManager.stopRecording()
                                                recordingTime = 0
                                            } else {
                                                var success = RecordingManager.startRecording(
                                                    saveFolderPath,
                                                    sessionName.length > 0 ? sessionName : generateSessionName(),
                                                    channelNamesList,
                                                    cameraId,
                                                    backend.samplingRate
                                                )
                                                if (success) {
                                                    recordingTime = 0
                                                }
                                            }
                                        }

                                        function generateSessionName() {
                                            var now = new Date()
                                            function pad(n) { return n < 10 ? "0" + n : "" + n }
                                            return "REC_" +
                                                   now.getFullYear() +
                                                   pad(now.getMonth() + 1) +
                                                   pad(now.getDate()) + "_" +
                                                   pad(now.getHours()) +
                                                   pad(now.getMinutes()) +
                                                   pad(now.getSeconds())
                                        }
                                    }

                                    Button {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 40
                                        text: isPaused ? "▶ Resume" : "⏸ Pause"
                                        font.pixelSize: 11
                                        enabled: isRecording
                                        palette.button: warningColor
                                        palette.buttonText: "white"
                                        onClicked: {
                                            if (isPaused) {
                                                RecordingManager.resumeRecording()
                                            } else {
                                                RecordingManager.pauseRecording()
                                            }
                                        }
                                    }

                                }

                                // EVENT MARKERS
                                ControlSection {
                                    title: "🏷️ Event Markers"
                                    textColor: eegWindow.textColor

                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 2
                                        columnSpacing: 8
                                        rowSpacing: 8

                                        MarkerButton {
                                            text: "👁️ Eyes Open"
                                            markerType: "eyes_open"
                                            buttonColor: "#3498db"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }

                                        MarkerButton {
                                            text: "😴 Eyes Closed"
                                            markerType: "eyes_closed"
                                            buttonColor: "#9b59b6"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }

                                        MarkerButton {
                                            text: "⚡ Seizure Start"
                                            markerType: "seizure_start"
                                            buttonColor: "#e74c3c"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }

                                        MarkerButton {
                                            text: "✓ Seizure Stop"
                                            markerType: "seizure_stop"
                                            buttonColor: "#27ae60"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }

                                        MarkerButton {
                                            text: "⚠️ Artifact"
                                            markerType: "artifact"
                                            buttonColor: "#f39c12"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }

                                        MarkerButton {
                                            text: "✏️ Custom"
                                            markerType: "custom"
                                            buttonColor: "#95a5a6"
                                            onMarkerClicked: function(type) { addMarker(type) }
                                        }
                                    }
                                }

                                // DISPLAY PARAMETERS
                                ControlSection {
                                    title: "⚙️ Display Parameters"
                                    textColor: eegWindow.textColor

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 5

                                        RowLayout {
                                            Layout.fillWidth: true

                                            Label {
                                                text: "Time Window:"
                                                font.pixelSize: 11
                                                color: textSecondary
                                                Layout.fillWidth: true
                                            }

                                            Label {
                                                text: timeSlider.value.toFixed(0) + "s"
                                                font.pixelSize: 11
                                                font.bold: true
                                                color: accentColor
                                            }
                                        }

                                        Slider {
                                            id: timeSlider
                                            Layout.fillWidth: true
                                            from: 5
                                            to: 30
                                            value: 10
                                            stepSize: 1
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 5

                                        RowLayout {
                                            Layout.fillWidth: true

                                            Label {
                                                text: "Sensitivity:"
                                                font.pixelSize: 11
                                                color: textSecondary
                                                Layout.fillWidth: true
                                            }

                                            Label {
                                                text: backend.scaler.sensitivity.toFixed(0) + " μV/mm"
                                                font.pixelSize: 11
                                                font.bold: true
                                                color: accentColor
                                            }
                                        }

                                        ComboBox {
                                            id: sensitivityCombo
                                            Layout.fillWidth: true
                                            model: backend.scaler.sensitivityOptions
                                            currentIndex: backend.scaler.sensitivityOptions.indexOf(backend.scaler.sensitivity)

                                            displayText: currentValue + " μV/mm"

                                            delegate: ItemDelegate {
                                                width: sensitivityCombo.width
                                                text: modelData + " μV/mm"
                                                highlighted: sensitivityCombo.highlightedIndex === index
                                            }

                                            onActivated: function(index) {
                                                backend.scaler.sensitivity = backend.scaler.sensitivityOptions[index]
                                            }
                                        }
                                    }
                                }

                                // ACTIONS
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Rectangle {
                                        Layout.fillWidth: true
                                        height: 1
                                        color: "#2d3e50"
                                    }

                                    Button {
                                        Layout.fillWidth: true
                                        text: "❌ End Examination"
                                        font.pixelSize: 11
                                        Layout.preferredHeight: 40
                                        palette.button: dangerColor
                                        palette.buttonText: "white"

                                        onClicked: {
                                            eegWindow.close()
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }
                    }
                }

                // CENTRAL - EEG GRAPH
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "#0d0f12"

                    EegGraph {
                        id: eegGraph
                        anchors.fill: parent
                        anchors.margins: 10
                        timeWindowSeconds: timeSlider.value
                        channelNames: backend.channelNames
                        markerManager: backend.markerManager
                        scaler: backend.scaler
                    }

                    // Loading overlay - shown while waiting for stream connection
                    Rectangle {
                        id: loadingOverlay
                        anchors.fill: parent
                        color: "#e00d0f12"
                        visible: backend.isConnecting
                        z: 100

                        Behavior on opacity {
                            NumberAnimation { duration: 300 }
                        }

                        Column {
                            anchors.centerIn: parent
                            spacing: 20

                            // Spinning loader
                            Item {
                                width: 80
                                height: 80
                                anchors.horizontalCenter: parent.horizontalCenter

                                Rectangle {
                                    id: spinnerOuter
                                    anchors.fill: parent
                                    radius: 40
                                    color: "transparent"
                                    border.width: 4
                                    border.color: "#2d3e50"
                                }

                                Rectangle {
                                    id: spinnerArc
                                    width: 80
                                    height: 80
                                    radius: 40
                                    color: "transparent"
                                    border.width: 4
                                    border.color: accentColor

                                    // Create arc effect with clip
                                    layer.enabled: true
                                    layer.effect: Item {
                                        Rectangle {
                                            width: 40
                                            height: 80
                                            color: "transparent"
                                        }
                                    }

                                    RotationAnimation on rotation {
                                        from: 0
                                        to: 360
                                        duration: 1200
                                        loops: Animation.Infinite
                                        running: backend.isConnecting
                                    }
                                }

                                // Inner pulse
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 40
                                    height: 40
                                    radius: 20
                                    color: accentColor
                                    opacity: 0.3

                                    SequentialAnimation on scale {
                                        running: backend.isConnecting
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 0.8; to: 1.2; duration: 800; easing.type: Easing.InOutQuad }
                                        NumberAnimation { from: 1.2; to: 0.8; duration: 800; easing.type: Easing.InOutQuad }
                                    }
                                }

                                // EEG wave icon in center
                                Label {
                                    anchors.centerIn: parent
                                    text: "📊"
                                    font.pixelSize: 24
                                }
                            }

                            Label {
                                text: "Connecting to EEG Stream..."
                                font.pixelSize: 18
                                font.bold: true
                                color: textColor
                                anchors.horizontalCenter: parent.horizontalCenter
                            }

                            Label {
                                text: "Searching for LSL stream from amplifier"
                                font.pixelSize: 12
                                color: textSecondary
                                anchors.horizontalCenter: parent.horizontalCenter
                            }

                            // Animated dots
                            Row {
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 8

                                Repeater {
                                    model: 3

                                    Rectangle {
                                        width: 10
                                        height: 10
                                        radius: 5
                                        color: accentColor

                                        SequentialAnimation on opacity {
                                            running: backend.isConnecting
                                            loops: Animation.Infinite
                                            PauseAnimation { duration: index * 200 }
                                            NumberAnimation { from: 0.3; to: 1; duration: 400 }
                                            NumberAnimation { from: 1; to: 0.3; duration: 400 }
                                            PauseAnimation { duration: (2 - index) * 200 }
                                        }
                                    }
                                }
                            }
                        }
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

                    Label {
                        text: "Amplifier: " + (amplifierId || "—")
                        font.pixelSize: 10
                        color: textSecondary
                    }

                    Rectangle { width: 1; height: 20; color: "#2d3e50" }

                    Label {
                        text: backend.samplingRate > 0
                              ? backend.samplingRate.toFixed(0) + " Hz"
                              : "Detecting…"
                        font.pixelSize: 10
                        color: textSecondary
                    }

                    Rectangle { width: 1; height: 20; color: "#2d3e50" }

                    Label {
                        text: backend.scaler.sensitivity.toFixed(0) + " μV/mm"
                        font.pixelSize: 10
                        color: accentColor
                    }

                    // Disk space — only shown while recording
                    Rectangle {
                        width: 1; height: 20; color: "#2d3e50"
                        visible: isRecording
                    }

                    Label {
                        visible: isRecording
                        text: {
                            var mb = RecordingManager.diskSpaceMB
                            var hours = RecordingManager.estimatedRemainingHours
                            var timeStr = ""
                            if (hours >= 0) {
                                if (hours < 1) timeStr = " (~" + Math.round(hours * 60) + " min)"
                                else timeStr = " (~" + hours.toFixed(1) + " h)"
                            }
                            return mb + " MB remaining" + timeStr
                        }
                        font.pixelSize: 10
                        color: {
                            var mb = RecordingManager.diskSpaceMB
                            if (mb > 5000) return textSecondary
                            if (mb > 1000) return warningColor
                            return dangerColor
                        }
                    }

                    Item { Layout.fillWidth: true }

                    // EEG stream connection indicator
                    Rectangle {
                        width: 10; height: 10; radius: 5
                        color: backend.isConnecting ? warningColor
                             : (backend.isConnected ? successColor : dangerColor)

                        SequentialAnimation on opacity {
                            running: backend.isConnecting || backend.isConnected
                            loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.3; duration: backend.isConnecting ? 500 : 1500 }
                            NumberAnimation { from: 0.3; to: 1; duration: backend.isConnecting ? 500 : 1500 }
                        }
                    }

                    Label {
                        text: backend.isConnecting ? "Connecting…"
                            : (backend.isConnected ? "Connected" : "Disconnected")
                        font.pixelSize: 10
                        color: backend.isConnecting ? warningColor
                             : (backend.isConnected ? successColor : dangerColor)
                        font.bold: true
                    }
                }
            }
        }
    }

    // Recording Manager connections
    Connections {
        target: RecordingManager

        function onRecordingStopped(sessionName, savePath, duration, eegSize, videoSize, eegSamples, videoFrames, markerCount) {
            summaryDialog.sessionNameText = sessionName
            summaryDialog.savePathText = savePath
            summaryDialog.durationText = duration
            summaryDialog.eegSizeText = eegSize
            summaryDialog.videoSizeText = videoSize
            summaryDialog.eegSamplesText = eegSamples
            summaryDialog.videoFramesText = videoFrames
            summaryDialog.markerCountText = markerCount
            summaryDialog.open()
        }

        function onRecordingError(error) {
            errorDialog.text = error
            errorDialog.open()
        }

        function onDiskSpaceLow(remainingMB) {
            console.log("Disk space warning: " + remainingMB + " MB remaining")
            // The amber banner is bound to RecordingManager.diskSpaceWarning
            // so it appears automatically. This handler is for logging only.
        }
    }

    // Recording Summary Dialog
    Dialog {
        id: summaryDialog
        title: ""
        modal: true
        anchors.centerIn: parent
        width: 520
        padding: 0
        standardButtons: Dialog.Ok

        property string sessionNameText: ""
        property string savePathText: ""
        property string durationText: ""
        property string eegSizeText: ""
        property string videoSizeText: ""
        property int eegSamplesText: 0
        property int videoFramesText: 0
        property int markerCountText: 0

        background: Rectangle {
            color: "#1a2332"
            radius: 12
            border.color: "#2d3e50"
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            // Header with green success bar
            Rectangle {
                Layout.fillWidth: true
                height: 60
                color: "#27ae60"
                radius: 12

                // Square off bottom corners
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 12
                    color: parent.color
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 20
                    spacing: 12

                    Label {
                        text: "Recording Complete"
                        font.pixelSize: 18
                        font.bold: true
                        color: "white"
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: summaryDialog.durationText
                        font.pixelSize: 22
                        font.bold: true
                        color: "white"
                        font.family: "Consolas"
                    }
                }
            }

            // Session name
            Rectangle {
                Layout.fillWidth: true
                height: 36
                color: "#1e2d3d"

                Label {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    text: summaryDialog.sessionNameText
                    font.pixelSize: 12
                    font.family: "Consolas"
                    color: "#8e9baa"
                    verticalAlignment: Text.AlignVCenter
                }
            }

            // Stats grid
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: statsGrid.height + 30
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 15

                GridLayout {
                    id: statsGrid
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    columns: 3
                    columnSpacing: 12
                    rowSpacing: 12

                    // EEG Card
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        color: "#1e2d3d"
                        radius: 8

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 4

                            Label {
                                text: "EEG DATA"
                                font.pixelSize: 10
                                font.bold: true
                                color: "#3498db"
                                font.letterSpacing: 1
                            }

                            Label {
                                text: summaryDialog.eegSamplesText.toLocaleString()
                                font.pixelSize: 20
                                font.bold: true
                                color: "white"
                            }

                            Label {
                                text: "samples / " + summaryDialog.eegSizeText
                                font.pixelSize: 10
                                color: "#8e9baa"
                            }
                        }
                    }

                    // Video Card
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        color: "#1e2d3d"
                        radius: 8

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 4

                            Label {
                                text: "VIDEO"
                                font.pixelSize: 10
                                font.bold: true
                                color: "#e74c3c"
                                font.letterSpacing: 1
                            }

                            Label {
                                text: summaryDialog.videoFramesText.toLocaleString()
                                font.pixelSize: 20
                                font.bold: true
                                color: "white"
                            }

                            Label {
                                text: "frames / " + summaryDialog.videoSizeText
                                font.pixelSize: 10
                                color: "#8e9baa"
                            }
                        }
                    }

                    // Markers Card
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        color: "#1e2d3d"
                        radius: 8

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 4

                            Label {
                                text: "MARKERS"
                                font.pixelSize: 10
                                font.bold: true
                                color: "#f39c12"
                                font.letterSpacing: 1
                            }

                            Label {
                                text: summaryDialog.markerCountText
                                font.pixelSize: 20
                                font.bold: true
                                color: "white"
                            }

                            Label {
                                text: "events"
                                font.pixelSize: 10
                                color: "#8e9baa"
                            }
                        }
                    }
                }
            }

            // Save path
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 8
                Layout.bottomMargin: 15
                height: 36
                color: "#1e2d3d"
                radius: 6

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 6

                    Label {
                        text: "SAVED"
                        font.pixelSize: 9
                        font.bold: true
                        color: "#27ae60"
                        font.letterSpacing: 1
                    }

                    Label {
                        text: summaryDialog.savePathText
                        font.pixelSize: 11
                        color: "#8e9baa"
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    // Recording Error Dialog
    Dialog {
        id: errorDialog
        title: ""
        modal: true
        anchors.centerIn: parent
        width: 420
        padding: 0
        standardButtons: Dialog.Ok

        property alias text: errorLabel.text

        background: Rectangle {
            color: "#1a2332"
            radius: 10
            border.color: "#e74c3c"
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                height: 44
                color: "#e74c3c"
                radius: 10

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 10
                    color: parent.color
                }

                Label {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    text: "Recording Error"
                    font.pixelSize: 15
                    font.bold: true
                    color: "white"
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Label {
                id: errorLabel
                Layout.fillWidth: true
                Layout.margins: 16
                wrapMode: Text.WordWrap
                color: "#ecf0f1"
                font.pixelSize: 13
            }
        }
    }

    // Separate Video Window (child of EegWindow)
    Window {
        id: videoWindow
        width: 800
        height: 600
        minimumWidth: 400
        minimumHeight: 300
        title: "Video Recording - " + (CameraManager.currentCameraName || "No Camera")
        visible: eegWindow.cameraId !== ""
        flags: Qt.Window

        color: "#0e1419"

        property color panelColor: "#1a2332"
        property color accentColorVideo: "#4a90e2"
        property color successColorVideo: "#2ecc71"
        property color warningColorVideo: "#f39c12"
        property color dangerColorVideo: "#c0392b"
        property color textColorVideo: "#e8eef5"
        property color textSecondaryVideo: "#8a9cb5"

        Component.onCompleted: {
            if (eegWindow.cameraId !== "") {
                // Connect VideoOutput sink to CameraManager for direct display.
                // This must happen before startCapture() so the external sink
                // is already registered when the capture session routes frames.
                CameraManager.setExternalVideoSink(videoOutput.videoSink)

                // If the camera index somehow got reset (e.g. re-entering the window),
                // attempt to re-select the camera by matching the stored ID.
                if (CameraManager.currentCameraIndex < 0) {
                    var cams = CameraManager.availableCameras
                    for (var i = 0; i < cams.length; ++i) {
                        if (cams[i].id === eegWindow.cameraId) {
                            CameraManager.setCurrentCameraIndex(i)
                            break
                        }
                    }
                }

                // Delay capture start slightly to let the QML VideoOutput finish
                // binding its sink, and to let async camera drivers initialise.
                captureStartTimer.start()
            }
        }

        Timer {
            id: captureStartTimer
            interval: 250   // 250 ms — safe margin for async integrated camera drivers
            repeat: false
            onTriggered: {
                CameraManager.startCapture()
            }
        }

        onClosing: function(close) {
            CameraManager.stopCapture()
        }

        Column {
            anchors.fill: parent
            spacing: 0

            // TOP TOOLBAR
            Rectangle {
                width: parent.width
                height: 50
                color: videoWindow.panelColor

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 15
                    spacing: 15

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Text {
                            text: "📹"
                            font.pixelSize: 24
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                text: videoBackend.cameraName || "Video Recording"
                                font.pixelSize: 14
                                font.bold: true
                                color: videoWindow.textColorVideo
                            }

                            Text {
                                text: "LSL Synchronized"
                                font.pixelSize: 10
                                color: videoWindow.textSecondaryVideo
                            }
                        }
                    }

                    Item { width: 1; height: 1 }

                    Rectangle {
                        width: 120
                        height: 35
                        anchors.verticalCenter: parent.verticalCenter
                        color: CameraManager.isCapturing ? videoWindow.dangerColorVideo : "#2d3e50"
                        radius: 4

                        Row {
                            anchors.centerIn: parent
                            spacing: 8

                            Rectangle {
                                width: 10
                                height: 10
                                radius: 5
                                color: "white"
                                visible: CameraManager.isCapturing
                                anchors.verticalCenter: parent.verticalCenter

                                SequentialAnimation on opacity {
                                    running: CameraManager.isCapturing
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.3; duration: 500 }
                                    NumberAnimation { from: 0.3; to: 1; duration: 500 }
                                }
                            }

                            Text {
                                text: CameraManager.isCapturing ? "CAPTURING" : "STOPPED"
                                font.pixelSize: 11
                                font.bold: true
                                color: "white"
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }
            }

            // VIDEO DISPLAY
            Item {
                width: parent.width
                height: parent.height - 85

                VideoOutput {
                    id: videoOutput
                    anchors.fill: parent
                    anchors.margins: 10
                    fillMode: VideoOutput.PreserveAspectFit

                    Rectangle {
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 10
                        width: timestampColumn.width + 20
                        height: timestampColumn.height + 16
                        color: "#cc000000"
                        radius: 6
                        visible: CameraManager.isCapturing

                        Column {
                            id: timestampColumn
                            anchors.centerIn: parent
                            spacing: 4

                            Text {
                                text: "LSL Time"
                                font.pixelSize: 9
                                color: videoWindow.textSecondaryVideo
                            }

                            Text {
                                text: CameraManager.lastFrameTimestamp.toFixed(6)
                                font.pixelSize: 12
                                font.family: "monospace"
                                font.bold: true
                                color: videoWindow.accentColorVideo
                            }
                        }
                    }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 15
                    visible: !CameraManager.isCapturing

                    Text {
                        text: "📹"
                        font.pixelSize: 64
                        color: "#7f8c8d"
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Text {
                        text: "Starting video capture..."
                        font.pixelSize: 14
                        color: videoWindow.textSecondaryVideo
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
            }

            // STATUS BAR
            Rectangle {
                width: parent.width
                height: 35
                color: videoWindow.panelColor

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 15
                    spacing: 20

                    Text {
                        text: "FPS: " + CameraManager.currentFps.toFixed(1)
                        font.pixelSize: 10
                        color: CameraManager.currentFps > 20 ? videoWindow.successColorVideo :
                               (CameraManager.currentFps > 10 ? videoWindow.warningColorVideo : videoWindow.dangerColorVideo)
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Rectangle { width: 1; height: 20; color: "#2d3e50"; anchors.verticalCenter: parent.verticalCenter }

                    Text {
                        text: "Camera: " + (CameraManager.currentCameraName || "None")
                        font.pixelSize: 10
                        color: videoWindow.textSecondaryVideo
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Rectangle { width: 1; height: 20; color: "#2d3e50"; anchors.verticalCenter: parent.verticalCenter }

                    Text {
                        text: "Format: " + (CameraManager.currentFormatString || "Auto")
                        font.pixelSize: 10
                        color: videoWindow.textSecondaryVideo
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Rectangle { width: 1; height: 20; color: "#2d3e50"; anchors.verticalCenter: parent.verticalCenter }

                    Text {
                        text: "LSL: " + (CameraManager.lastFrameTimestamp > 0 ?
                              CameraManager.lastFrameTimestamp.toFixed(3) + "s" : "N/A")
                        font.pixelSize: 10
                        color: videoWindow.accentColorVideo
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Item { width: 1; height: 1 }

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 5

                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            color: CameraManager.isCapturing ? videoWindow.successColorVideo : videoWindow.dangerColorVideo
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: CameraManager.isCapturing ? "Capturing" : "Stopped"
                            font.pixelSize: 10
                            color: CameraManager.isCapturing ? videoWindow.successColorVideo : videoWindow.dangerColorVideo
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }
    }

    onClosing: function(close) {
        if (RecordingManager.isRecording) {
            RecordingManager.stopRecording()
        }
        backend.stopStream()
        if (videoWindow.visible) {
            CameraManager.stopCapture()
            videoWindow.close()
        }
        examinationEnded()
    }
}
