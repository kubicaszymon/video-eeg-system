import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: root

    property string markerType: ""
    property color buttonColor: "#3498db"

    signal markerClicked(string type)

    font.pixelSize: 10
    Layout.fillWidth: true
    Layout.preferredHeight: 35
    palette.button: buttonColor
    palette.buttonText: "white"

    onClicked: markerClicked(markerType)
}
