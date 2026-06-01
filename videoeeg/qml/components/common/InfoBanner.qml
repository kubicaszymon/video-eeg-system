import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string icon: "ℹ️"
    property string message: ""
    property color bannerColor: "#e8f4f8"
    property color bannerBorderColor: "#bee5eb"
    property color bannerTextColor: "#0c5460"

    Layout.fillWidth: true
    Layout.preferredHeight: 60
    color: bannerColor
    radius: 8
    border.color: bannerBorderColor
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 15
        spacing: 12

        Label {
            text: root.icon
            font.pixelSize: 24
        }

        Label {
            text: root.message
            font.pixelSize: 12
            color: root.bannerTextColor
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
    }
}
