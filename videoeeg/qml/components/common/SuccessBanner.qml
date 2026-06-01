import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""

    Layout.fillWidth: true
    Layout.preferredHeight: 60
    color: "#d4edda"
    radius: 8
    border.color: "#c3e6cb"
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 15
        spacing: 12

        Label {
            text: "✓"
            font.pixelSize: 20
            font.bold: true
            color: "#155724"
        }

        ColumnLayout {
            spacing: 2
            Layout.fillWidth: true

            Label {
                text: root.title
                font.pixelSize: 12
                font.bold: true
                color: "#155724"
            }

            Label {
                text: root.subtitle
                font.pixelSize: 11
                color: "#155724"
            }
        }
    }
}
