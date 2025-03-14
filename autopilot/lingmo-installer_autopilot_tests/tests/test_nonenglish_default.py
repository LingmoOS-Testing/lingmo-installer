# Testing Default Install for the Lingmo_installer Installer
# Author: Dan Chapman <daniel@chapman-mail.com>
# Copyright (C) 2013
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from lingmo_installer_autopilot_tests.tests import Lingmo_installerAutopilotTestCase
from testtools.matchers import Equals
from autopilot.matchers import Eventually
from lingmo_installer_autopilot_tests.emulators import gtktoplevel


class DefaultInstallTestCase(Lingmo_installerAutopilotTestCase):
    """
    A default install testcase just generally clicks through the installer
    using all the default values
    """

    def test_default_install(self, ):
        # first check we have an emulator instance
        flavor = self.get_distribution()
        self.assertIsInstance(self.main_window, gtktoplevel.GtkWindow)
        self.assertThat(self.main_window.visible, Eventually(Equals(True)))
        self.welcome_page_tests()
        self.go_to_next_page()
        self.keyboard_layout_page_tests()
        self.go_to_next_page()
        self.preparing_page_tests()
        self.go_to_next_page()
        if flavor == 'Edlingmo':
            self.edlingmo_addon_window_tests(ltsp=True)
            self.go_to_next_page()
            self.edlingmo_packages_window_tests()
            self.go_to_next_page()
        self.installation_type_page_tests(default=True)
        self.go_to_next_page(wait=True)
        self.location_page_tests()
        self.go_to_next_page()
        self.user_info_page_tests('Autopilot', 'password')
        self.go_to_progress_page()

        self.progress_page_tests()
        self.assertThat(lambda: self.app.select_single(
            'GtkDialog',
            name='finished_dialog').visible,
            Eventually(Equals(True), timeout=180))
        # XXX: Uncomment if you want to restart after install complete
        # we need to sleep here to wait for dialog to fully load. It appears
        # in dbus before its actually visible. As the test has already passed
        # this doesn't affect outcome
        # time.sleep(5)
        #
        # self.keyboard.press_and_release('Enter')
