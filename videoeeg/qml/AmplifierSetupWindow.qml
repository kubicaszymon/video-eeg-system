import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia
import videoEeg

Window {
    id: window
    visible: false
    width: 1200
    height: 750
    title: qsTr("⚡ EEG Examination Configuration")
    modality: Qt.ApplicationModal

    signal accepted(config: var)
    signal rejected()

    property var channelSelectionModel: []
    property string savePath: ""
    property int currentStep: 1
    property int channelUpdateCounter: 0  // Trigger to force UI update

    readonly property color bgColor: "#f5f7fa"
    readonly property color sidebarColor: "#2c3e50"
    readonly property color cardColor: "#ffffff"
    readonly property color accentColor: "#3498db"
    readonly property color successColor: "#2ecc71"
    readonly property color textColor: "#2c3e50"
    readonly property color borderColor: "#e0e6ed"
    readonly property color hoverColor: "#ecf0f1"

    AmplifierSetupBackend {
        id: backend

        onCurrentChannelsChanged: {
            var newModel = []
            for (var i = 0; i < backend.currentChannels.length; i++) {
                newModel.push(false)
            }
            channelSelectionModel = newModel
            channelUpdateCounter++
            console.log("Channels changed, initialized model with", newModel.length, "channels")
        }

        Component.onCompleted: {
            // Refresh camera list when backend is ready
            backend.refreshCameraList()
        }

        Component.onDestruction: {
            // Stop camera preview when window closes
            backend.stopCameraPreview()
        }
    }

    // Video sink for camera preview
    VideoOutput {
        id: cameraPreviewOutput
        visible: false  // Hidden, used only to provide sink
    }

    FolderDialog {
        id: folderDialog
        title: "Select Recording Save Folder"
        onAccepted: {
            savePath = selectedFolder.toString().replace("file:///", "")
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

    function isChannelSelected(idx) {
        void(channelUpdateCounter)  // Dependency on update counter
        return channelSelectionModel[idx] === true
    }

    function getSelectedChannelsCount() {
        void(channelUpdateCounter)
        var count = 0
        for (var i = 0; i < channelSelectionModel.length; i++) {
            if (channelSelectionModel[i]) count++
        }
        return count
    }

    function areAllChannelsSelected() {
        void(channelUpdateCounter)
        if (channelSelectionModel.length === 0) return false
        for (var i = 0; i < channelSelectionModel.length; i++) {
            if (!channelSelectionModel[i]) return false
        }
        return true
    }

    function toggleChannel(index) {
        var newModel = channelSelectionModel.slice()
        newModel[index] = !newModel[index]
        channelSelectionModel = newModel
        channelUpdateCounter++
        console.log("Toggle channel", index, "->", newModel[index], "counter:", channelUpdateCounter)
    }

    function selectAllChannels(selectAll) {
        var newModel = []
        var channelCount = backend.currentChannels.length
        for (var i = 0; i < channelCount; i++) {
            newModel.push(selectAll)
        }
        channelSelectionModel = newModel
        channelUpdateCounter++
        console.log("Select all:", selectAll, "channelCount:", channelCount, "counter:", channelUpdateCounter)
    }

    function getSelectedChannelsList() {
        var selected = []
        for (var i = 0; i < channelSelectionModel.length; i++) {
            if (channelSelectionModel[i]) {
                selected.push(backend.currentChannels[i])
            }
        }
        return selected
    }

    function getCurrentStepNumber() {
        return currentStep
    }

    function getCurrentStepTitle() {
        var step = getCurrentStepNumber()
        switch(step) {
            case 1: return "Step 1: Amplifier Selection"
            case 2: return "Step 2: Channel Selection"
            case 3: return "Step 3: Camera Selection"
            case 4: return "Step 4: Summary"
            default: return ""
        }
    }

    function getCurrentStepDesc() {
        var step = getCurrentStepNumber()
        switch(step) {
            case 1: return "Detect and select EEG amplifier"
            case 2: return "Select channels to record"
            case 3: return "Select camera for video recording"
            case 4: return "Review configuration before starting"
            default: return ""
        }
    }

    Rectangle {
        anchors.fill: parent
        color: bgColor

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // HEADER WITH PROGRESS
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                color: sidebarColor

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 15

                    Label {
                        text: "⚡"
                        font.pixelSize: 32
                        color: "white"
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: getCurrentStepTitle()
                            font.pixelSize: 18
                            font.bold: true
                            color: "white"
                        }

                        Label {
                            text: getCurrentStepDesc()
                            font.pixelSize: 12
                            color: "#95a5a6"
                        }
                    }

                    // Progress indicator (4 steps)
                    Row {
                        spacing: 10

                        Repeater {
                            model: 4

                            Row {
                                spacing: 10

                                Rectangle {
                                    width: 35
                                    height: 35
                                    radius: 17.5
                                    color: getCurrentStepNumber() > index ? successColor :
                                           getCurrentStepNumber() === index + 1 ? accentColor : "#7f8c8d"
                                    border.color: "white"
                                    border.width: 2

                                    Label {
                                        anchors.centerIn: parent
                                        text: getCurrentStepNumber() > index ? "✓" : (index + 1).toString()
                                        font.pixelSize: getCurrentStepNumber() > index ? 16 : 14
                                        font.bold: true
                                        color: "white"
                                    }
                                }

                                Rectangle {
                                    width: 40
                                    height: 2
                                    color: getCurrentStepNumber() > index + 1 ? successColor : "#7f8c8d"
                                    visible: index < 3
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }
                }
            }

            // CONTENT
            StackView {
                id: stackView
                Layout.fillWidth: true
                Layout.fillHeight: true
                initialItem: amplifierSelectionPage

                pushEnter: Transition {
                    PropertyAnimation { property: "opacity"; from: 0; to: 1; duration: 200 }
                }
                pushExit: Transition {
                    PropertyAnimation { property: "opacity"; from: 1; to: 0; duration: 200 }
                }
                popEnter: Transition {
                    PropertyAnimation { property: "opacity"; from: 0; to: 1; duration: 200 }
                }
                popExit: Transition {
                    PropertyAnimation { property: "opacity"; from: 1; to: 0; duration: 200 }
                }
            }
        }

        // LOADING OVERLAY - positioned over entire window content
        Rectangle {
            anchors.fill: parent
            color: "#cc1a1a2e"
            visible: backend.isLoading
            opacity: backend.isLoading ? 1 : 0
            z: 1000

            Behavior on opacity {
                NumberAnimation { duration: 200 }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {} // Block clicks
            }

            Rectangle {
                anchors.centerIn: parent
                width: 280
                height: 200
                radius: 16
                color: cardColor
                border.color: accentColor
                border.width: 2

                layer.enabled: true

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 20

                    // Custom spinning loader
                    Item {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: 60

                        Rectangle {
                            id: spinnerOuter
                            anchors.centerIn: parent
                            width: 60
                            height: 60
                            radius: 30
                            color: "transparent"
                            border.color: borderColor
                            border.width: 4
                        }

                        Rectangle {
                            id: spinnerArc
                            anchors.centerIn: parent
                            width: 60
                            height: 60
                            radius: 30
                            color: "transparent"
                            border.color: accentColor
                            border.width: 4

                            Rectangle {
                                width: 32
                                height: 32
                                color: cardColor
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Rectangle {
                                width: 32
                                height: 32
                                color: cardColor
                                anchors.bottom: parent.bottom
                                anchors.horizontalCenter: parent.horizontalCenter
                            }

                            RotationAnimation on rotation {
                                from: 0
                                to: 360
                                duration: 1000
                                loops: Animation.Infinite
                                running: backend.isLoading
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            text: "🔍"
                            font.pixelSize: 20
                        }
                    }

                    ColumnLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 6

                        Label {
                            text: "Scanning for devices..."
                            font.pixelSize: 15
                            font.bold: true
                            color: textColor
                            Layout.alignment: Qt.AlignHCenter
                        }

                        Label {
                            text: "Looking for EEG amplifiers"
                            font.pixelSize: 12
                            color: "#7f8c8d"
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }

                    // Animated dots
                    Row {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 6

                        Repeater {
                            model: 3

                            Rectangle {
                                width: 8
                                height: 8
                                radius: 4
                                color: accentColor

                                SequentialAnimation on opacity {
                                    loops: Animation.Infinite
                                    running: backend.isLoading

                                    PauseAnimation { duration: index * 200 }
                                    NumberAnimation { from: 0.3; to: 1; duration: 300 }
                                    NumberAnimation { from: 1; to: 0.3; duration: 300 }
                                    PauseAnimation { duration: (2 - index) * 200 }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // STEP 1: AMPLIFIER SELECTION
    Component {
        id: amplifierSelectionPage

        Rectangle {
            color: bgColor

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 30
                spacing: 20

                InfoBanner {
                    icon: "ℹ️"
                    message: "Make sure the amplifier is turned on and connected to the computer"
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: cardColor
                    radius: 8
                    border.color: borderColor
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 15

                        SectionHeader {
                            icon: "🔌"
                            title: "Detected Amplifiers"
                            count: backend.availableAmplifiers.length
                            textColor: window.textColor
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: borderColor
                        }

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            ListView {
                                id: amplifierListView
                                model: backend.availableAmplifiers
                                spacing: 10

                                delegate: DeviceCard {
                                    icon: "⚡"
                                    deviceName: modelData
                                    deviceInfo: "Virtual Amplifier • Ready"
                                    isSelected: backend.selectedAmplifierIndex === index
                                    accentColor: window.accentColor
                                    cardColor: window.cardColor
                                    hoverColor: window.hoverColor
                                    textColor: window.textColor
                                    borderColor: window.borderColor
                                    successColor: window.successColor
                                    onClicked: backend.selectedAmplifierIndex = index
                                }

                                Label {
                                    anchors.centerIn: parent
                                    visible: amplifierListView.count === 0
                                    text: "😔 No amplifiers found\nClick 'Refresh' to scan again"
                                    font.pixelSize: 13
                                    color: "#999999"
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                    }
                }

                NavigationBar {
                    showBack: false
                    showRefresh: true
                    refreshText: "🔄 Refresh"
                    refreshEnabled: !backend.isLoading
                    nextEnabled: backend.selectedAmplifierIndex !== -1
                    nextColor: accentColor

                    onRefreshClicked: {
                        backend.refreshAmplifiersList()
                    }
                    onCancelClicked: {
                        rejected()
                        window.close()
                    }
                    onNextClicked: {
                        currentStep = 2
                        stackView.push(channelSelectionPage)
                    }
                }
            }
        }
    }

    // STEP 2: CHANNEL SELECTION
    Component {
        id: channelSelectionPage

        Rectangle {
            color: bgColor

            // Local properties that react to channelUpdateCounter
            property bool allSelected: {
                void(channelUpdateCounter)
                return areAllChannelsSelected()
            }
            property int selectedCount: {
                void(channelUpdateCounter)
                return getSelectedChannelsCount()
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 30
                spacing: 20

                SuccessBanner {
                    title: "Selected amplifier: " + backend.availableAmplifiers[backend.selectedAmplifierIndex]
                    subtitle: backend.currentChannels.length + " available channels"
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: cardColor
                    radius: 8
                    border.color: borderColor
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        // Header row
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 50
                            color: "#f8f9fa"
                            radius: 8

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                anchors.rightMargin: 20

                                Label {
                                    text: "No."
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: textColor
                                    Layout.preferredWidth: 60
                                }

                                Label {
                                    text: "Channel Name"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: textColor
                                    Layout.fillWidth: true
                                }

                                // Select All checkbox
                                Rectangle {
                                    width: selectAllRow.width + 16
                                    height: 30
                                    radius: 4
                                    color: selectAllMouse.containsMouse ? hoverColor : "transparent"

                                    Row {
                                        id: selectAllRow
                                        anchors.centerIn: parent
                                        spacing: 8

                                        Rectangle {
                                            width: 18
                                            height: 18
                                            radius: 3
                                            border.color: allSelected ? accentColor : "#bdc3c7"
                                            border.width: 2
                                            color: allSelected ? accentColor : "white"

                                            Text {
                                                anchors.centerIn: parent
                                                text: "✓"
                                                font.pixelSize: 14
                                                font.bold: true
                                                color: "white"
                                                visible: allSelected
                                            }
                                        }

                                        Text {
                                            text: "Select all"
                                            font.pixelSize: 12
                                            color: textColor
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }

                                    MouseArea {
                                        id: selectAllMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            selectAllChannels(!allSelected)
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: borderColor
                        }

                        // Channel list
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            ListView {
                                id: channelListView
                                model: backend.currentChannels
                                spacing: 0

                                delegate: Rectangle {
                                    id: channelRow
                                    width: channelListView.width
                                    height: 45

                                    property bool isSelected: {
                                        void(channelUpdateCounter)
                                        return isChannelSelected(index)
                                    }

                                    color: isSelected ? "#e8f4f8" : (index % 2 === 0 ? "white" : "#f8f9fa")

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 20
                                        anchors.rightMargin: 20
                                        spacing: 15

                                        Label {
                                            text: (index + 1).toString()
                                            font.pixelSize: 12
                                            color: textColor
                                            Layout.preferredWidth: 60
                                        }

                                        Label {
                                            text: modelData
                                            font.pixelSize: 12
                                            color: textColor
                                            Layout.fillWidth: true
                                        }

                                        // Channel checkbox
                                        Rectangle {
                                            width: 18
                                            height: 18
                                            radius: 3
                                            border.color: channelRow.isSelected ? accentColor : "#bdc3c7"
                                            border.width: 2
                                            color: channelRow.isSelected ? accentColor : "white"

                                            Text {
                                                anchors.centerIn: parent
                                                text: "✓"
                                                font.pixelSize: 14
                                                font.bold: true
                                                color: "white"
                                                visible: channelRow.isSelected
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    toggleChannel(index)
                                                }
                                            }
                                        }
                                    }

                                    // Make whole row clickable
                                    MouseArea {
                                        anchors.fill: parent
                                        z: -1
                                        onClicked: {
                                            toggleChannel(index)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                NavigationBar {
                    showBack: true
                    middleText: selectedCount + " / " + backend.currentChannels.length + " selected"
                    nextEnabled: selectedCount > 0
                    nextColor: accentColor

                    onBackClicked: {
                        currentStep = 1
                        stackView.pop()
                    }
                    onCancelClicked: {
                        rejected()
                        window.close()
                    }
                    onNextClicked: {
                        currentStep = 3
                        stackView.push(cameraSelectionPage)
                    }
                }
            }
        }
    }

    // STEP 3: CAMERA SELECTION
    Component {
        id: cameraSelectionPage

        Rectangle {
            color: bgColor

            // Start preview when page becomes active
            Component.onCompleted: {
                if (backend.selectedCameraIndex >= 0) {
                    backend.startCameraPreview()
                }
            }

            Component.onDestruction: {
                backend.stopCameraPreview()
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 30
                spacing: 20

                InfoBanner {
                    icon: "📹"
                    message: "Select a camera to synchronize video with EEG data (optional)"
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 20

                    // Left panel: Camera list and settings
                    Rectangle {
                        Layout.preferredWidth: 400
                        Layout.fillHeight: true
                        color: cardColor
                        radius: 8
                        border.color: borderColor
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 20
                            spacing: 15

                            SectionHeader {
                                icon: "📷"
                                title: "Available Cameras"
                                count: backend.availableCameras.length
                                textColor: window.textColor
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: borderColor
                            }

                            ScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true

                                ListView {
                                    id: cameraListView
                                    model: backend.availableCameras
                                    spacing: 10

                                    delegate: DeviceCard {
                                        icon: modelData.isDefault ? "📹" : "📷"
                                        deviceName: modelData.description
                                        deviceInfo: modelData.formatCount + " formats available" + (modelData.isDefault ? " (Default)" : "")
                                        isSelected: backend.selectedCameraIndex === index
                                        accentColor: window.accentColor
                                        cardColor: window.cardColor
                                        hoverColor: window.hoverColor
                                        textColor: window.textColor
                                        borderColor: window.borderColor
                                        successColor: window.successColor
                                        onClicked: {
                                            backend.setSelectedCameraIndex(index)
                                            backend.startCameraPreview()
                                        }
                                    }

                                    Label {
                                        anchors.centerIn: parent
                                        visible: cameraListView.count === 0
                                        text: "No cameras found\nClick 'Refresh' to scan again"
                                        font.pixelSize: 13
                                        color: "#999999"
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                }
                            }

                            // Format selection
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: formatColumn.implicitHeight + 20
                                color: "#f8f9fa"
                                radius: 6
                                visible: backend.selectedCameraIndex >= 0

                                ColumnLayout {
                                    id: formatColumn
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 8

                                    Label {
                                        text: "Resolution & FPS"
                                        font.pixelSize: 11
                                        font.bold: true
                                        color: textColor
                                    }

                                    ComboBox {
                                        id: formatCombo
                                        Layout.fillWidth: true
                                        model: backend.availableFormats
                                        currentIndex: backend.selectedFormatIndex
                                        textRole: "displayString"

                                        delegate: ItemDelegate {
                                            width: formatCombo.width
                                            text: modelData.displayString
                                            highlighted: formatCombo.highlightedIndex === index
                                        }

                                        onActivated: function(index) {
                                            backend.setSelectedFormatIndex(index)
                                        }
                                    }
                                }
                            }

                            // Option: no camera
                            Rectangle {
                                Layout.fillWidth: true
                                height: 50
                                color: backend.selectedCameraIndex === -1 ? "#fff3cd" : cardColor
                                radius: 6
                                border.color: backend.selectedCameraIndex === -1 ? "#ffc107" : borderColor
                                border.width: backend.selectedCameraIndex === -1 ? 2 : 1

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        backend.stopCameraPreview()
                                        backend.setSelectedCameraIndex(-1)
                                    }
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 10

                                    Label {
                                        text: "⊘"
                                        font.pixelSize: 18
                                        color: "#856404"
                                    }

                                    Label {
                                        text: "Continue without camera"
                                        font.pixelSize: 11
                                        font.bold: backend.selectedCameraIndex === -1
                                        color: "#856404"
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }

                    // Right panel: Camera preview
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "#1a1a2e"
                        radius: 8
                        border.color: borderColor
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 0

                            // Preview header
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                color: "#2d3e50"
                                radius: 8

                                // Fix bottom corners
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    height: 8
                                    color: parent.color
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 15
                                    anchors.rightMargin: 15

                                    Label {
                                        text: "Live Preview"
                                        font.pixelSize: 12
                                        font.bold: true
                                        color: "white"
                                    }

                                    Item { Layout.fillWidth: true }

                                    Rectangle {
                                        width: 10
                                        height: 10
                                        radius: 5
                                        color: backend.isCameraPreviewActive ? "#2ecc71" : "#e74c3c"

                                        SequentialAnimation on opacity {
                                            running: backend.isCameraPreviewActive
                                            loops: Animation.Infinite
                                            NumberAnimation { from: 1; to: 0.3; duration: 800 }
                                            NumberAnimation { from: 0.3; to: 1; duration: 800 }
                                        }
                                    }

                                    Label {
                                        text: backend.isCameraPreviewActive ? "Active" : "Inactive"
                                        font.pixelSize: 10
                                        color: backend.isCameraPreviewActive ? "#2ecc71" : "#e74c3c"
                                    }
                                }
                            }

                            // Preview area
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                VideoOutput {
                                    id: previewVideoOutput
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    fillMode: VideoOutput.PreserveAspectFit
                                    visible: backend.isCameraPreviewActive && backend.selectedCameraIndex >= 0

                                    Component.onCompleted: {
                                        if (backend.cameraManager) {
                                            backend.cameraManager.setExternalVideoSink(previewVideoOutput.videoSink)
                                        }
                                    }
                                }

                                // Placeholder when no camera selected
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 15
                                    visible: !backend.isCameraPreviewActive || backend.selectedCameraIndex < 0

                                    Label {
                                        text: "📷"
                                        font.pixelSize: 64
                                        color: "#7f8c8d"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                    }

                                    Label {
                                        text: backend.selectedCameraIndex < 0 ?
                                              "Select a camera to see preview" :
                                              "Starting preview..."
                                        font.pixelSize: 14
                                        color: "#95a5a6"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                    }
                                }
                            }

                            // Preview footer with info
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                color: "#2d3e50"
                                radius: 8

                                // Fix top corners
                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    height: 8
                                    color: parent.color
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 15
                                    anchors.rightMargin: 15

                                    Label {
                                        text: backend.selectedCameraName || "No camera"
                                        font.pixelSize: 10
                                        color: "#95a5a6"
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    Label {
                                        text: backend.selectedFormatString || ""
                                        font.pixelSize: 10
                                        color: accentColor
                                        visible: backend.selectedCameraIndex >= 0
                                    }
                                }
                            }
                        }
                    }
                }

                NavigationBar {
                    showBack: true
                    showRefresh: true
                    refreshText: "Refresh cameras"
                    nextColor: accentColor

                    onRefreshClicked: {
                        backend.refreshCameraList()
                    }
                    onBackClicked: {
                        backend.stopCameraPreview()
                        currentStep = 2
                        stackView.pop()
                    }
                    onCancelClicked: {
                        backend.stopCameraPreview()
                        rejected()
                        window.close()
                    }
                    onNextClicked: {
                        backend.stopCameraPreview()
                        currentStep = 4
                        stackView.push(summaryPage)
                    }
                }
            }
        }
    }

    // STEP 4: SUMMARY
    Component {
        id: summaryPage

        Rectangle {
            color: bgColor

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 30
                spacing: 20

                Label {
                    text: "✅ Configuration Summary"
                    font.pixelSize: 18
                    font.bold: true
                    color: textColor
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 15

                        // Amplifier
                        Rectangle {
                            Layout.fillWidth: true
                            height: contentCol1.implicitHeight + 30
                            color: cardColor
                            radius: 8
                            border.color: borderColor
                            border.width: 1

                            ColumnLayout {
                                id: contentCol1
                                anchors.fill: parent
                                anchors.margins: 15
                                spacing: 8

                                Label {
                                    text: "⚡ Amplifier"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: textColor
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: borderColor
                                }

                                Label {
                                    text: backend.availableAmplifiers[backend.selectedAmplifierIndex]
                                    font.pixelSize: 13
                                    color: "#7f8c8d"
                                }
                            }
                        }

                        // Channels
                        Rectangle {
                            Layout.fillWidth: true
                            height: contentCol2.implicitHeight + 30
                            color: cardColor
                            radius: 8
                            border.color: borderColor
                            border.width: 1

                            ColumnLayout {
                                id: contentCol2
                                anchors.fill: parent
                                anchors.margins: 15
                                spacing: 8

                                Label {
                                    text: "🔌 Selected Channels (" + getSelectedChannelsCount() + ")"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: textColor
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: borderColor
                                }

                                Label {
                                    text: getSelectedChannelsList().join(", ")
                                    font.pixelSize: 12
                                    color: "#7f8c8d"
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        // Camera
                        Rectangle {
                            Layout.fillWidth: true
                            height: contentCol3.implicitHeight + 30
                            color: cardColor
                            radius: 8
                            border.color: borderColor
                            border.width: 1

                            ColumnLayout {
                                id: contentCol3
                                anchors.fill: parent
                                anchors.margins: 15
                                spacing: 8

                                Label {
                                    text: "📹 Camera"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: textColor
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: borderColor
                                }

                                Label {
                                    text: backend.selectedCameraIndex >= 0 ?
                                          backend.selectedCameraName + " (" + backend.selectedFormatString + ")" :
                                          "None (EEG only)"
                                    font.pixelSize: 13
                                    color: "#7f8c8d"
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        // Save location
                        Rectangle {
                            Layout.fillWidth: true
                            height: contentCol4.implicitHeight + 30
                            color: cardColor
                            radius: 8
                            border.color: borderColor
                            border.width: 1

                            ColumnLayout {
                                id: contentCol4
                                anchors.fill: parent
                                anchors.margins: 15
                                spacing: 8

                                Label {
                                    text: "💾 Recording Save Location"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: textColor
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: borderColor
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10

                                    TextField {
                                        Layout.fillWidth: true
                                        text: savePath || "Select save folder..."
                                        readOnly: true
                                        font.pixelSize: 11
                                    }

                                    Button {
                                        text: "📁 Browse"
                                        font.pixelSize: 11
                                        Layout.preferredHeight: 35
                                        onClicked: folderDialog.open()
                                    }
                                }

                                Label {
                                    text: savePath ? "Session: " + generateSessionName() : "Please select a save folder"
                                    font.pixelSize: 11
                                    color: savePath ? "#27ae60" : "#e74c3c"
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                }

                NavigationBar {
                    showBack: true
                    nextText: "✓ Start Examination"
                    nextColor: successColor

                    onBackClicked: {
                        currentStep = 3
                        stackView.pop()
                    }
                    onCancelClicked: {
                        rejected()
                        window.close()
                    }
                    nextEnabled: savePath !== ""
                    onNextClicked: {
                        var selectedChannels = []
                        for (var i = 0; i < channelSelectionModel.length; i++) {
                            if (channelSelectionModel[i]) {
                                selectedChannels.push(i)
                            }
                        }
                        var cameraId = backend.getSelectedCameraId()
                        var config = {
                            amplifierId: backend.getSelectedAmplifierId(),
                            channels: selectedChannels,
                            cameraId: cameraId,
                            saveFolderPath: savePath,
                            sessionName: generateSessionName(),
                            channelNames: getSelectedChannelsList()
                        }
                        console.log("Starting examination with", selectedChannels.length, "channels")
                        console.log("Camera ID:", cameraId || "none")
                        console.log("Save path:", savePath)
                        console.log("Session:", config.sessionName)
                        accepted(config)
                        window.close()
                    }
                }
            }
        }
    }
}
