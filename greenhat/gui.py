import sys
import socket
import threading
import datetime
import logging

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QLineEdit, QPushButton)
from PyQt5.QtGui import QPalette, QPixmap, QTransform

import greenhat


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.image_label = QLabel()
        self.image_label.setBackgroundRole(QPalette.Base)
        self.pixmap = QPixmap()
        self.setCentralWidget(self.image_label)

        self.w_ip_address = QLineEdit()
        self.w_ip_address.setPlaceholderText('IP Address')
        self.w_connect = QPushButton()
        self.w_connect.setText('Connect')
        self.w_connect.clicked.connect(self.connect)
        self.w_patch_wifi = QPushButton('Patch WiFi')
        self.w_patch_wifi.setText('Patch WiFi')
        self.w_patch_wifi.clicked.connect(self.patch_wifi)

        self.w_screenshot = QPushButton()
        self.w_screenshot.setText('Screenshot')
        self.w_screenshot.clicked.connect(self.screenshot)

        self.w_toolbar = self.addToolBar('toolbar')
        self.w_toolbar.addWidget(self.w_ip_address)
        self.w_toolbar.addWidget(self.w_connect)
        self.w_toolbar.addWidget(self.w_patch_wifi)
        self.w_toolbar.addWidget(self.w_screenshot)

        self.packet_handler = greenhat.PacketHandler(timeout=0.1)
        self.thread = threading.Thread(target=self.thread_target)
        self.alive = True
        self.thread.start()

        self.client = None

        self.top_image = None

    def load_image(self, bytes):
        self.pixmap.loadFromData(bytes)
        self.image_label.setPixmap(
            self.pixmap
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
                    self.top_image = image
        self.packet_handler.close()

    def get_client(self, ip) -> greenhat.Client:
        if self.client is None or self.client.ip != ip:
            self.client = greenhat.Client(ip=ip)
        return self.client

    def connect(self):
        threading.Thread(
            target=self.get_client(self.w_ip_address.text()).remoteplay
        ).start()

    def patch_wifi(self):
        threading.Thread(
            target=self.get_client(self.w_ip_address.text()).patch_wifi
        ).start()

    def screenshot(self):
        now = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S.%f')[:-3]
        if self.top_image is not None:
            filename = '%s-top.jpeg' % now
            self.image_label.pixmap().save(filename, 'JPEG')
            logging.info('image saved to %s' % filename)


def main():
    logging.basicConfig(
        format='[%(asctime)-15s] %(message)s', level=logging.DEBUG)
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
