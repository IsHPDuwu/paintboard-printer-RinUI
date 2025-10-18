import QtQuick
import QtQuick.Controls
import QtQuick.Window
import RinUI

Window {
    width: 1250 // Increased width to accommodate layout
    height: 900  // Increased height for controls below
    visible: true
    title: qsTr("LGS Paintboard 2026")

    Connections {
        target: wsClient
        function onBoard_updated(base64Image) { paintboardImage.source = base64Image }
        function onHeatmap_updated(base64Image) { heatmapImage.source = base64Image }
        function onPaint_result(paint_id, status) { statusText.text = "Paint result: " + status }
        function onMessage_received(msg) { statusText.text = msg }
    }

    // Main layout is now a Column
    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        // Top Row: Login controls and Paintboard
        Row {
            width: parent.width
            spacing: 10

            // Left panel for login and controls
            Column {
                width: 200
                spacing: 10

                TextField { id: uidField; placeholderText: qsTr("UID") }
                TextField { id: accessKeyField; placeholderText: qsTr("Access Key") }
                Button {
                    text: qsTr("Get Token")
                    onClicked: {
                        statusText.text = "Getting token..."
                        var token = apiHandler.get_token(uidField.text, accessKeyField.text)
                        tokenText.text = token
                        if (token.startsWith("Error:")) {
                            statusText.text = token
                        } else {
                            statusText.text = "Token received!"
                        }
                    }
                }
                TextField { id: tokenText; placeholderText: qsTr("Token"); readOnly: true }
            }

            // Center panel for the paintboard
            Item {
                width: 1000
                height: 600

                Image { id: paintboardImage; anchors.fill: parent; source: ""; fillMode: Image.PreserveAspectFit }
                Image { id: heatmapImage; anchors.fill: parent; source: ""; visible: heatmapSwitch.checked; fillMode: Image.PreserveAspectFit }
                MouseArea {
                    anchors.fill: parent
                    property color selectedColor: "red"
                    onClicked: (mouse) => {
                        wsClient.paint(parseInt(uidField.text), tokenText.text, selectedColor.r * 255, selectedColor.g * 255, selectedColor.b * 255, mouse.x, mouse.y)
                    }
                }
            }
        }

        // Bottom Row: Color picker and other controls
        Row {
            width: parent.width
            height: 100
            spacing: 20

            // Color Palette
            Column {
                spacing: 5
                Text { text: qsTr("Color Palette") }
                GridView {
                    id: colorPicker
                    width: 150
                    height: 100
                    cellWidth: 20
                    cellHeight: 20
                    model: ["red", "green", "blue", "yellow", "black", "white", "purple", "orange", "cyan", "magenta"]
                    delegate: Rectangle {
                        width: 20; height: 20
                        color: modelData; border.color: "gray"
                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                // Find the MouseArea for painting and set its color
                                paintboardImage.parent.children[2].selectedColor = modelData
                            }
                        }
                    }
                }
            }

            // Options
            Column {
                spacing: 5
                Text { text: qsTr("Options") }
                Switch { id: heatmapSwitch; text: qsTr("Show Heatmap"); checked: false }
            }

            // Status
            Column {
                spacing: 5
                Text { text: qsTr("Status") }
                Text { id: statusText; text: qsTr("Status: Not connected"); wrapMode: Text.WordWrap }
            }
        }
    }
}
