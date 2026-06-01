import QtQuick
import QtQuick.Controls
import QtQuick.Window
import videoEeg

ApplicationWindow {
    id: root
    visible: true
    width: Screen.width
    height: Screen.height
    visibility: Window.Maximized
    title: qsTr("VideoEEG - Main Menu")

    // Reference to dynamically created EegWindow
    property var eegWindowInstance: null

    Loader {
        id: contentLoader
        anchors.fill: parent
        source: "MainWindow.qml"
    }

    Connections {
        target: contentLoader.item
        ignoreUnknownSignals: true

        function onEegWindowOpen(config) {
            console.log("Opening EEG window with config:", JSON.stringify(config))

            // Create EegWindow dynamically
            var component = Qt.createComponent("EegWindow.qml")
            if (component.status === Component.Ready) {
                eegWindowInstance = component.createObject(null, {
                    "amplifierId": config.amplifierId,
                    "channels": config.channels,
                    "cameraId": config.cameraId || "",
                    "saveFolderPath": config.saveFolderPath || "",
                    "sessionName": config.sessionName || "",
                    "channelNamesList": config.channelNames || []
                })

                // Connect to examinationEnded signal
                eegWindowInstance.examinationEnded.connect(function() {
                    console.log("Examination ended signal received")
                    root.visible = true
                    root.raise()
                    eegWindowInstance = null
                })

                // Hide main window
                root.visible = false

                console.log("EegWindow created and main window hidden")
            } else if (component.status === Component.Error) {
                console.error("Error creating EegWindow:", component.errorString())
            }
        }
    }

    // Cleanup on application exit
    onClosing: function(close) {
        if (eegWindowInstance) {
            eegWindowInstance.close()
            eegWindowInstance = null
        }
    }
}
