# -*- coding: utf-8 -*-

import sys

from PyQt5 import QtWidgets, uic
from lingmo_installer.frontend.kde_components.Timezone import TimezoneMap


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setStyle("Oxygen")
    qss = open("/usr/share/lingmo_installer/qt/style.qss").read()
    app.setStyleSheet(qss)

    page = uic.loadUi('/usr/share/lingmo_installer/qt/stepLocation.ui')
    tzmap = TimezoneMap(page.map_frame)
    page.map_frame.layout().addWidget(tzmap)
    page.show()

    sys.exit(app.exec_())
