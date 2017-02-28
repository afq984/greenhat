import sys
import socket
import threading

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.QtGui import QPalette, QPixmap, QTransform

import greenhat


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.image_label = QLabel()
        self.image_label.setBackgroundRole(QPalette.Base)
        self.setCentralWidget(self.image_label)

        self.packet_handler = greenhat.PacketHandler(timeout=0.1)
        self.thread = threading.Thread(target=self.thread_target)
        self.alive = True
        self.thread.start()

    def load_image(self, bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(bytes)
        self.image_label.setPixmap(
            pixmap
            .transformed(
                QTransform().rotate(-90)
            )
        )

    def closeEvent(self, event):
        self.alive = False
        event.accept()

    def thread_target(self):
        while self.alive:
            try:
                screen, image = self.packet_handler.recv_packet()
            except socket.timeout:
                pass
            else:
                if image is not None and screen == greenhat.Screen.TOP:
                    self.load_image(image)
        self.packet_handler.close()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
