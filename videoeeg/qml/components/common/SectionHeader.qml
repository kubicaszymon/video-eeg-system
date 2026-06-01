import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root

    property string icon: ""
    property string title: ""
    property int count: 0
    property color textColor: "#2c3e50"

    Layout.fillWidth: true

    Label {
        text: root.icon + " " + root.title
        font.pixelSize: 16
        font.bold: true
        color: root.textColor
        Layout.fillWidth: true
    }

    Label {
        text: root.count + " found"
        font.pixelSize: 12
        color: "#7f8c8d"
    }
}
