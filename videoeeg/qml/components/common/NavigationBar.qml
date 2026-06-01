import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root

    property bool showBack: true
    property bool showRefresh: false
    property string refreshText: "🔄 Refresh"
    property bool refreshEnabled: true
    property string nextText: "Next →"
    property bool nextEnabled: true
    property color nextColor: "#3498db"
    property string middleText: ""

    signal backClicked()
    signal cancelClicked()
    signal nextClicked()
    signal refreshClicked()

    Layout.fillWidth: true
    spacing: 15

    Button {
        visible: root.showRefresh
        text: root.refreshText
        font.pixelSize: 13
        enabled: root.refreshEnabled
        Layout.preferredWidth: 140
        Layout.preferredHeight: 45
        palette.button: "#95a5a6"
        palette.buttonText: "white"
        onClicked: root.refreshClicked()
    }

    Button {
        visible: root.showBack && !root.showRefresh
        text: "← Back"
        font.pixelSize: 13
        Layout.preferredWidth: 120
        Layout.preferredHeight: 45
        onClicked: root.backClicked()
    }

    Item { Layout.fillWidth: true }

    Label {
        visible: root.middleText !== ""
        text: root.middleText
        font.pixelSize: 12
        color: "#7f8c8d"
    }

    Button {
        visible: root.showBack && root.showRefresh
        text: "← Back"
        font.pixelSize: 13
        Layout.preferredWidth: 120
        Layout.preferredHeight: 45
        onClicked: root.backClicked()
    }

    Button {
        text: "Cancel"
        font.pixelSize: 13
        Layout.preferredWidth: 100
        Layout.preferredHeight: 45
        onClicked: root.cancelClicked()
    }

    Button {
        text: root.nextText
        font.pixelSize: 13
        font.bold: true
        enabled: root.nextEnabled
        Layout.preferredWidth: root.nextText.length > 10 ? 180 : 120
        Layout.preferredHeight: 45
        palette.button: root.nextColor
        palette.buttonText: "white"
        onClicked: root.nextClicked()
    }
}
