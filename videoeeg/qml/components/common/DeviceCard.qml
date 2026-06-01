import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string icon: "⚡"
    property string deviceName: ""
    property string deviceInfo: ""
    property bool isSelected: false
    property color accentColor: "#3498db"
    property color cardColor: "#ffffff"
    property color hoverColor: "#ecf0f1"
    property color textColor: "#2c3e50"
    property color borderColor: "#e0e6ed"
    property color successColor: "#2ecc71"

    signal clicked()

    width: ListView.view ? ListView.view.width : parent.width
    height: 80
    color: isSelected ? "#e8f4f8" : cardColor
    radius: 6
    border.color: isSelected ? accentColor : borderColor
    border.width: isSelected ? 2 : 1

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: parent.color = root.isSelected ? "#e8f4f8" : root.hoverColor
        onExited: parent.color = root.isSelected ? "#e8f4f8" : root.cardColor
        onClicked: root.clicked()
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 15
        spacing: 15

        Rectangle {
            Layout.preferredWidth: 50
            Layout.preferredHeight: 50
            radius: 25
            color: root.isSelected ? root.accentColor : "#ecf0f1"

            Label {
                anchors.centerIn: parent
                text: root.icon
                font.pixelSize: 24
                color: root.isSelected ? "white" : root.textColor
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            Label {
                text: root.deviceName
                font.pixelSize: 14
                font.bold: true
                color: root.textColor
            }

            Label {
                text: root.deviceInfo
                font.pixelSize: 11
                color: "#7f8c8d"
            }
        }

        Rectangle {
            visible: root.isSelected
            Layout.preferredWidth: 24
            Layout.preferredHeight: 24
            radius: 12
            color: root.successColor

            Label {
                anchors.centerIn: parent
                text: "✓"
                font.pixelSize: 14
                font.bold: true
                color: "white"
            }
        }
    }
}
