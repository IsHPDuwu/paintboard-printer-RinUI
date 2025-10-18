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
        function onBoard_received(boardData) {
            paintboardCanvas.updateBoard(boardData)
        }
        function onPaint_event(x, y, r, g, b) {
            paintboardCanvas.updatePixel(x, y, Qt.rgba(r/255.0, g/255.0, b/255.0, 1))
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
        Canvas {
            id: paintboardCanvas
            width: 1000
            height: 600

            property color selectedColor: "red"

            function updatePixel(x, y, color) {
                var ctx = getContext("2d")
                ctx.fillStyle = color
                ctx.fillRect(x, y, 1, 1)
                requestPaint()
            }

            function updateBoard(boardData) {
                var ctx = getContext("2d")
                var imageData = ctx.createImageData(1000, 600)
                var data = imageData.data

                for (var i = 0; i < boardData.length; i++) {
                    var pixel = boardData[i] // [x, y, r, g, b]
                    var index = (pixel[1] * 1000 + pixel[0]) * 4
                    data[index] = pixel[2]
                    data[index + 1] = pixel[3]
                    data[index + 2] = pixel[4]
                    data[index + 3] = 255 // Alpha
                }

                ctx.putImageData(imageData, 0, 0)
                requestPaint()
            }

            onPaint: {
                // The board is painted by updateBoard and updatePixel,
                // so we don't need to do anything here.
                // An explicit onPaint handler is still needed for requestPaint() to work.
            }

            MouseArea {
                anchors.fill: parent
                onClicked: (mouse) => {
                    wsClient.paint(
                        parseInt(uidField.text),
                        tokenText.text,
                        paintboardCanvas.selectedColor.r * 255,
                        paintboardCanvas.selectedColor.g * 255,
                        paintboardCanvas.selectedColor.b * 255,
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
                            paintboardCanvas.selectedColor = modelData
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
