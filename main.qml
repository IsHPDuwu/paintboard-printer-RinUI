import QtQuick
import QtQuick.Controls
import QtQuick.Window
import RinUI

Window {
    width: 1200
    height: 800
    visible: true
    title: qsTr("LGS Paintboard 2026")

    Connections {
        target: wsClient
        function onBoard_updated(base64Image) {
            paintboardImage.source = base64Image
        }
        function onPaint_result(paint_id, status) {
            statusText.text = "Paint result: " + status
        }
        function onMessage_received(msg) {
            statusText.text = msg
        }
    }

    // Main layout
    Row {
        anchors.fill: parent
        spacing: 10

        // Left panel for login and controls
        Column {
            width: 200
            spacing: 10
            anchors.margins: 10

            TextField {
                id: uidField
                placeholderText: qsTr("UID")
            }
            TextField {
                id: accessKeyField
                placeholderText: qsTr("Access Key")
            }
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
            TextField {
                id: tokenText
                placeholderText: qsTr("Token")
                readOnly: true
            }
        }

        // Center panel for the paintboard
        Item {
            width: 1000
            height: 600

            Image {
                id: paintboardImage
                anchors.fill: parent
                // The source will be set dynamically from the backend.
                // An empty source is valid and will not produce an error.
                source: ""
                fillMode: Image.PreserveAspectFit
            }

            MouseArea {
                anchors.fill: parent
                property color selectedColor: "red"
                onClicked: (mouse) => {
                    wsClient.paint(
                        parseInt(uidField.text),
                        tokenText.text,
                        selectedColor.r * 255,
                        selectedColor.g * 255,
                        selectedColor.b * 255,
                        mouse.x,
                        mouse.y
                    )
                }
            }
        }

        // Right panel for color selection and status
        Column {
            width: 150
            spacing: 10
            anchors.margins: 10

            Text {
                text: qsTr("Color Palette")
            }

            GridView {
                width: parent.width
                height: 100
                cellWidth: 20
                cellHeight: 20
                model: ["red", "green", "blue", "yellow", "black", "white"]

                delegate: Rectangle {
                    width: 20
                    height: 20
                    color: modelData
                    border.color: "gray"

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            paintboardImage.parent.children[1].selectedColor = modelData
                        }
                    }
                }
            }

            Text {
                id: statusText
                text: qsTr("Status: Not connected")
                wrapMode: Text.WordWrap
            }
        }
    }
}
