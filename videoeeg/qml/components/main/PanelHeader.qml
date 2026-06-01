import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string icon: ""
    property string title: ""
    property string buttonText: ""
    property color buttonColor: "#2ecc71"
    property color headerColor: "#2c3e50"

    signal buttonClicked()

    Layout.fillWidth: true
    Layout.preferredHeight: 60
    color: headerColor

    RowLayout {
        anchors.fill: parent
        anchors.margins: 15
        spacing: 10

        Label {
            text: root.icon + " " + root.title
            font.pixelSize: 18
            font.bold: true
            color: "white"
            Layout.fillWidth: true
        }

        Button {
            visible: root.buttonText !== ""
            text: root.buttonText
            font.pixelSize: 12
            font.bold: root.buttonText.length > 10
            Layout.preferredWidth: root.buttonText.length > 10 ? 180 : 80
            Layout.preferredHeight: root.buttonText.length > 10 ? 40 : 35
            palette.button: root.buttonColor
            palette.buttonText: "white"
            onClicked: root.buttonClicked()
        }
    }
}
