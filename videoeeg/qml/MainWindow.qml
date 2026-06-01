import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import videoEeg

Item {
    id: mainWindow
    signal eegWindowOpen(config: var)

    // Hospital colors
    readonly property color bgColor: "#f5f7fa"
    readonly property color sidebarColor: "#2c3e50"
    readonly property color cardColor: "#ffffff"
    readonly property color accentColor: "#3498db"
    readonly property color textColor: "#2c3e50"
    readonly property color borderColor: "#e0e6ed"
    readonly property color hoverColor: "#ecf0f1"

    // Crash recovery state
    property var recoveredSession: ({})
    property bool hasRecoverableSession: false

    Rectangle {
        anchors.fill: parent
        color: bgColor

        RowLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // LEFT SECTION - PATIENTS
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: parent.width * 0.35
                Layout.minimumWidth: 400
                color: cardColor
                border.color: borderColor
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 0
                    spacing: 0

                    PanelHeader {
                        icon: "👤"
                        title: "Patients"
                        buttonText: "+ New"
                        buttonColor: "#2ecc71"
                        headerColor: sidebarColor
                    }

                    // Search bar
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        color: "white"
                        border.color: borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 5

                            Label {
                                text: "🔍"
                                font.pixelSize: 16
                            }

                            TextField {
                                Layout.fillWidth: true
                                placeholderText: "Search patient (ID, surname...)"
                                font.pixelSize: 12
                            }
                        }
                    }

                    // Patient list
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        ListView {
                            anchors.fill: parent
                            model: 8
                            spacing: 1

                            delegate: PatientListItem {
                                patientName: "Jan Kowalski"
                                patientId: "85010112345"
                                lastExamination: "10.01.2025"
                                textColor: mainWindow.textColor
                                hoverColor: mainWindow.hoverColor
                                borderColor: mainWindow.borderColor
                            }
                        }
                    }
                }
            }

            // RIGHT SECTION - EXAMINATIONS
            Rectangle {
                Layout.fillHeight: true
                Layout.fillWidth: true
                color: bgColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 0
                    spacing: 0

                    PanelHeader {
                        icon: "📊"
                        title: "EEG Examinations"
                        buttonText: "⚡ New EEG Examination"
                        buttonColor: accentColor
                        headerColor: sidebarColor
                        onButtonClicked: amplifierSetupWindow.show()
                    }

                    // Filters bar
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        color: "white"
                        border.color: borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 15
                            anchors.rightMargin: 15
                            spacing: 15

                            Label {
                                text: "Filter:"
                                font.pixelSize: 12
                                color: textColor
                            }

                            ComboBox {
                                Layout.preferredWidth: 150
                                Layout.preferredHeight: 30
                                model: ["All", "Today", "This week", "This month"]
                                font.pixelSize: 11
                            }

                            ComboBox {
                                Layout.preferredWidth: 150
                                Layout.preferredHeight: 30
                                model: ["All statuses", "Completed", "In progress", "Cancelled"]
                                font.pixelSize: 11
                            }

                            Item { Layout.fillWidth: true }

                            Label {
                                text: "Sort:"
                                font.pixelSize: 12
                                color: textColor
                            }

                            ComboBox {
                                Layout.preferredWidth: 150
                                Layout.preferredHeight: 30
                                model: ["Newest", "Oldest", "By patient"]
                                font.pixelSize: 11
                            }
                        }
                    }

                    // Examination list
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth

                        Flow {
                            width: parent.width
                            padding: 15
                            spacing: 15

                            Repeater {
                                model: 6

                                Rectangle {
                                    width: (parent.width - parent.padding * 2 - parent.spacing) / 2
                                    height: 200
                                    color: cardColor
                                    radius: 8
                                    border.color: cardMouseArea.containsMouse ? accentColor : borderColor
                                    border.width: cardMouseArea.containsMouse ? 2 : 1

                                    MouseArea {
                                        id: cardMouseArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                    }

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 15
                                        spacing: 8

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 10

                                            Rectangle {
                                                Layout.preferredWidth: 50
                                                Layout.preferredHeight: 50
                                                color: "#e8f4f8"
                                                radius: 25

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "📈"
                                                    font.pixelSize: 24
                                                }
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Label {
                                                    text: "Jan Kowalski"
                                                    font.pixelSize: 14
                                                    font.bold: true
                                                    color: textColor
                                                    elide: Text.ElideRight
                                                    Layout.fillWidth: true
                                                }

                                                Label {
                                                    text: "EEG - Standard examination"
                                                    font.pixelSize: 11
                                                    color: "#7f8c8d"
                                                    elide: Text.ElideRight
                                                    Layout.fillWidth: true
                                                }
                                            }

                                            StatusBadge {
                                                status: "Completed"
                                            }
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 1
                                            color: borderColor
                                        }

                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 10
                                            rowSpacing: 5

                                            Label {
                                                text: "📅 Date:"
                                                font.pixelSize: 11
                                                color: "#7f8c8d"
                                            }

                                            Label {
                                                text: "14.01.2025 10:30"
                                                font.pixelSize: 11
                                                color: textColor
                                                Layout.fillWidth: true
                                            }

                                            Label {
                                                text: "⏱️ Duration:"
                                                font.pixelSize: 11
                                                color: "#7f8c8d"
                                            }

                                            Label {
                                                text: "45 min"
                                                font.pixelSize: 11
                                                color: textColor
                                                Layout.fillWidth: true
                                            }

                                            Label {
                                                text: "🔌 Channels:"
                                                font.pixelSize: 11
                                                color: "#7f8c8d"
                                            }

                                            Label {
                                                text: "14 channels"
                                                font.pixelSize: 11
                                                color: textColor
                                                Layout.fillWidth: true
                                            }
                                        }

                                        Item { Layout.fillHeight: true }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Button {
                                                text: "👁️ Preview"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 30
                                            }

                                            Button {
                                                text: "📄 Report"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 30
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    AmplifierSetupWindow {
        id: amplifierSetupWindow
        onAccepted: function(config) {
            eegWindowOpen(config)
        }

        onRejected: {
            console.log("Setup cancelled")
        }
    }

    // ================================================================
    // CRASH RECOVERY — Detect and offer to resume interrupted sessions
    // ================================================================

    FolderDialog {
        id: recoveryFolderDialog
        title: "Select folder with interrupted recording session"
        onAccepted: {
            var folderPath = selectedFolder.toString().replace("file:///", "")
            var state = RecordingManager.checkForUnfinishedSession(folderPath)
            if (Object.keys(state).length > 0) {
                recoveredSession = state
                hasRecoverableSession = true
                recoveryDialog.open()
            } else {
                noSessionDialog.open()
            }
        }
    }

    Dialog {
        id: noSessionDialog
        title: "No Interrupted Session"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Ok

        Label {
            text: "No interrupted recording sessions were found in the selected folder."
            wrapMode: Text.WordWrap
            width: 300
        }
    }

    // Recovery confirmation dialog
    Dialog {
        id: recoveryDialog
        title: ""
        modal: true
        anchors.centerIn: parent
        width: 520
        padding: 0
        standardButtons: Dialog.NoButton

        background: Rectangle {
            color: "#1a2332"
            radius: 12
            border.color: "#f39c12"
            border.width: 2
        }

        contentItem: ColumnLayout {
            spacing: 0

            // Header
            Rectangle {
                Layout.fillWidth: true
                height: 55
                color: "#f39c12"
                radius: 12

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
                    spacing: 10

                    Label {
                        text: "Interrupted Session Detected"
                        font.pixelSize: 16
                        font.bold: true
                        color: "#1a1a1a"
                    }
                }
            }

            // Session info
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 20
                spacing: 12

                Label {
                    text: "A previous recording session was not closed properly (power loss or crash)."
                    font.pixelSize: 13
                    color: "#e8eef5"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: infoColumn.height + 20
                    color: "#1e2d3d"
                    radius: 8

                    ColumnLayout {
                        id: infoColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 10
                        spacing: 6

                        Label {
                            text: "Session: " + (recoveredSession.sessionName || "unknown")
                            font.pixelSize: 12
                            font.family: "Consolas"
                            color: "#8a9cb5"
                        }

                        Label {
                            text: "Last active: " + (recoveredSession.lastWallClock || "unknown")
                            font.pixelSize: 12
                            font.family: "Consolas"
                            color: "#8a9cb5"
                        }

                        Label {
                            text: "Samples recorded: " + (recoveredSession.recordedSamples || 0).toLocaleString()
                            font.pixelSize: 12
                            font.family: "Consolas"
                            color: "#8a9cb5"
                        }

                        Label {
                            text: "Folder: " + (recoveredSession.saveFolderPath || "unknown")
                            font.pixelSize: 11
                            font.family: "Consolas"
                            color: "#6a7b8b"
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                    }
                }

                Label {
                    text: "The existing data files (EEG CSV, markers, video) are intact.\nYou can start a new session that appends to the same folder with a GAP marker."
                    font.pixelSize: 12
                    color: "#8a9cb5"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                // Buttons
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Button {
                        text: "Resume (New Session in Same Folder)"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        palette.button: "#f39c12"
                        palette.buttonText: "#1a1a1a"

                        onClicked: {
                            recoveryDialog.close()
                            // Open the EEG window with the recovered config.
                            // The recording will start fresh but in the same folder,
                            // so clinicians can reconstruct the timeline post-hoc.
                            // Channel indices are reconstructed as sequential 0..N-1
                            // since the amplifier must be re-connected from scratch.
                            var chNames = recoveredSession.channelNames || []
                            var chIndices = []
                            for (var i = 0; i < chNames.length; i++) chIndices.push(i)

                            var config = {
                                amplifierId: recoveredSession.amplifierId || "",
                                channels: chIndices,
                                cameraId: recoveredSession.cameraId || "",
                                saveFolderPath: recoveredSession.saveFolderPath || "",
                                sessionName: (recoveredSession.sessionName || "REC") + "_resumed",
                                channelNames: chNames
                            }
                            console.log("Resuming session:", JSON.stringify(config))
                            eegWindowOpen(config)
                        }
                    }

                    Button {
                        text: "Discard"
                        font.pixelSize: 12
                        Layout.preferredWidth: 100
                        Layout.preferredHeight: 42
                        palette.button: "#2d3e50"
                        palette.buttonText: "#e8eef5"

                        onClicked: {
                            recoveryDialog.close()
                            hasRecoverableSession = false
                        }
                    }
                }
            }
        }
    }

    // "Recover Session" button in the main UI
    Rectangle {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 20
        width: recoverRow.width + 24
        height: 38
        radius: 6
        color: "#2c3e50"
        z: 10

        Row {
            id: recoverRow
            anchors.centerIn: parent
            spacing: 8

            Label {
                text: "Recover Interrupted Session"
                font.pixelSize: 11
                color: "#ecf0f1"
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: recoveryFolderDialog.open()
        }
    }
}
