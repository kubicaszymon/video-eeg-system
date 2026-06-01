import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string status: "Completed"
    property color badgeColor: "#d4edda"
    property color badgeBorderColor: "#c3e6cb"
    property color badgeTextColor: "#155724"

    Layout.preferredWidth: 80
    Layout.preferredHeight: 24
    color: badgeColor
    radius: 12
    border.color: badgeBorderColor
    border.width: 1

    Label {
        anchors.centerIn: parent
        text: root.status
        font.pixelSize: 9
        color: root.badgeTextColor
    }
}
