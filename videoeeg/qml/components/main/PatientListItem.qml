import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string patientName: ""
    property string patientId: ""
    property string lastExamination: ""
    property color textColor: "#2c3e50"
    property color hoverColor: "#ecf0f1"
    property color borderColor: "#e0e6ed"

    signal clicked()

    width: ListView.view ? ListView.view.width : parent.width
    height: 80
    color: mouseArea.containsMouse ? hoverColor : "white"
    border.color: borderColor
    border.width: 1

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 4

        Label {
            text: root.patientName
            font.pixelSize: 14
            font.bold: true
            color: root.textColor
        }

        Label {
            text: "ID: " + root.patientId
            font.pixelSize: 11
            color: "#7f8c8d"
        }

        Label {
            text: "Last examination: " + root.lastExamination
            font.pixelSize: 11
            color: "#7f8c8d"
        }
    }
}
