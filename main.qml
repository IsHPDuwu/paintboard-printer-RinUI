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
            paintboardCanvas.boardModel = boardData
            paintboardCanvas.requestPaint()
        }
        function onPaint_event(x, y, r, g, b) {
            var index = y * 1000 + x
            if (paintboardCanvas.boardModel && paintboardCanvas.boardModel.length > index) {
                paintboardCanvas.boardModel[index] = [x, y, r, g, b]
                paintboardCanvas.requestPaint()
            }
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
            property var boardModel: []

            onPaint: {
                var ctx = getContext("2d")
                if (boardModel.length === 0) {
                    ctx.fillStyle = "white"
                    ctx.fillRect(0, 0, width, height)
                    return
                }

                var imageData = ctx.createImageData(1000, 600)
                var data = imageData.data

                for (var i = 0; i < boardModel.length; i++) {
                    var pixel = boardModel[i] // [x, y, r, g, b]
                    var index = (pixel[1] * 1000 + pixel[0]) * 4
                    data[index] = pixel[2]
                    data[index + 1] = pixel[3]
                    data[index + 2] = pixel[4]
                    data[index + 3] = 255 // Alpha
                }

                ctx.putImageData(imageData, 0, 0)
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
