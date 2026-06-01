import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    property string title: ""
    property color textColor: "#e8eef5"
    property color dividerColor: "#2d3e50"

    default property alias content: contentContainer.data

    Layout.fillWidth: true
    spacing: 10

    Label {
        text: root.title
        font.pixelSize: 13
        font.bold: true
        color: root.textColor
    }

    Rectangle {
        Layout.fillWidth: true
        height: 1
        color: root.dividerColor
    }

    ColumnLayout {
        id: contentContainer
        Layout.fillWidth: true
        spacing: 8
    }
}
