# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2013 Canonical Ltd.
# Written by Evan Dandrea <evan.dandrea@canonical.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import glob
import os
import subprocess
import sys
import syslog

from lingmo_installer import i18n, misc, osextras, plugin, upower
from lingmo_installer.install_misc import (archdetect, is_secure_boot,
                                           minimal_install_rlist_path)

NAME = 'prepare'
AFTER = 'wireless'
WEIGHT = 11
OEM = False


# TODO: This cannot be a non-debconf plugin after all as OEMs may want to
# preseed the 'install updates' and 'install non-free software' options.  So?
# Just db_get them.  No need for any other overhead, surely.  Actually, you
# need the dbfilter for that get.

class PreparePageBase(plugin.PluginUI):
    plugin_title = 'lingmo_installer/text/prepare_heading_label'
    download_updates = True
    download_updates_enabled = True

    def __init__(self, *args, **kwargs):
        plugin.PluginUI.__init__(self)

    def plugin_set_online_state(self, state):
        # if we're disabling, remember what it was before so we can re-enable
        # properly if network comes back
        if self.prepare_network_connection.get_state() and not state:
            self.download_updates = self.get_download_updates()
        self.prepare_network_connection.set_state(state)
        self.enable_download_updates(state)
        self.download_updates_enabled = state
        if not state:
            self.set_download_updates(False)
        else:
            self.set_download_updates(self.download_updates)

    def set_sufficient_space(self, state, required, free):
        if not state:
            # There's either no drives present, or not enough free space.
            # Either way, we cannot continue.
            self.show_insufficient_space_page(required, free)
            self.controller.allow_go_forward(False)
        self.prepare_sufficient_space.set_state(state)

    def plugin_translate(self, lang):
        self.rst_title_text = i18n.get_string('rst_header', lang)
        return

    def show_lingmo_drivers_spinner(self):
        return

    def hide_lingmo_drivers_spinner(self):
        return


class PageGtk(PreparePageBase):
    restricted_package_name = 'lingmo-restricted-addons'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        from lingmo_installer.gtkwidgets import Builder
        builder = Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['LINGMO_INSTALLER_GLADE'], 'stepPrepare.ui'))
        builder.connect_signals(self)

        # Get all objects + add internal child(s)
        all_widgets = builder.get_object_ids()
        for wdg in all_widgets:
            setattr(self, wdg, builder.get_object(wdg))

        self.password_strength_pages = {
            'empty': 0,
            'too_short': 1,
            'good': 2,
        }
        self.password_match_pages = {
            'empty': 0,
            'mismatch': 1,
            'ok': 2,
        }

        if upower.has_battery():
            upower.setup_power_watch(self.prepare_power_source)
        else:
            self.prepare_power_source.hide()
        self.prepare_network_connection = builder.get_object(
            'prepare_network_connection')

        self.using_secureboot = False

        self.secureboot_box.set_sensitive(False)
        self.password_grid.set_sensitive(False)

        self.minimal_install_vbox.set_visible(
            os.path.exists(minimal_install_rlist_path))

        self.prepare_page = builder.get_object('stepPrepare')
        self.insufficient_space_page = builder.get_object('stepNoSpace')
        self.rst_page = builder.get_object('stepRST')
        self.rst_label = builder.get_object('label_using_rst')
        self.rst_label.connect('activate-link', self.on_link_clicked)
        self.current_page = self.prepare_page
        self.plugin_widgets = self.prepare_page
        self.plugin_optional_widgets = [self.insufficient_space_page,
                                        self.rst_page]

    def on_link_clicked(self, widget, uri):
        misc.launch_uri(uri)

    def plugin_get_current_page(self):
        return self.current_page

    def show_insufficient_space_page(self, required, free):
        self.current_page = self.insufficient_space_page

        self.label_required_space.set_label(required)
        self.label_free_space.set_label(free)

        self.controller.go_to_page(self.current_page)

    def show_rst_page(self):
        for page in self.controller._wizard.pages:
            if page.module.NAME == NAME:
                page.title = 'lingmo_installer/text/rst_header'
                break
        self.current_page = self.rst_page
        self.controller.go_to_page(self.current_page)
        return True

    def show_lingmo_drivers_spinner(self):
        frontend = self.controller._wizard
        frontend.status_spinner.show()
        frontend.status_spinner.start()
        frontend.status_label.show()

    def hide_lingmo_drivers_spinner(self):
        frontend = self.controller._wizard
        frontend.status_spinner.hide()
        frontend.status_spinner.stop()
        frontend.status_label.hide()

    def plugin_on_next_clicked(self):
        if self.current_page != self.rst_page:
            if self.get_use_nonfree():
                self.show_lingmo_drivers_spinner()
            return

        self.controller._wizard.do_reboot()
        return True

    def set_using_secureboot(self, secureboot):
        self.using_secureboot = secureboot
        self.secureboot_box.set_visible(secureboot)
        self.disable_secureboot.set_active(True)
        self.on_nonfree_toggled(None)
        self.info_loop(None)

    def enable_download_updates(self, val):
        if (val):
            template = 'lingmo_installer/text/label_download_updates'
        else:
            template = 'lingmo_installer/text/label_download_updates_na'
        self.label_download_updates.set_label(
            self.controller.get_string(template))
        self.prepare_download_updates.set_sensitive(val)

    def set_download_updates(self, val):
        self.prepare_download_updates.set_active(val)

    def get_download_updates(self):
        return self.prepare_download_updates.get_active()

    def set_minimal_install(self, val):
        self.prepare_minimal_install.set_active(val)

    def get_minimal_install(self):
        return self.prepare_minimal_install.get_active()

    def set_allow_nonfree(self, allow):
        if not allow:
            self.prepare_nonfree_software.set_active(False)
            self.nonfree_vbox.set_property('visible', False)

    def set_use_nonfree(self, val):
        if osextras.find_on_path('lingmo-drivers'):
            self.prepare_nonfree_software.set_active(val)
        else:
            self.debug('Could not find lingmo-drivers on the executable path.')
            self.set_allow_nonfree(False)

    def get_use_nonfree(self):
        return self.prepare_nonfree_software.get_active()

    def get_disable_secureboot(self):
        return self.disable_secureboot.get_active()

    def plugin_translate(self, lang):
        PreparePageBase.plugin_translate(self, lang)

        frontend = self.controller._wizard
        frontend.status_label.set_text(self.controller.get_string(
            'lingmo_installer/text/preparing_ud_label', lang))

        release = misc.get_release()

        from gi.repository import Gtk
        for widget in [self.prepare_download_updates,
                       self.label_required_space,
                       self.label_free_space]:
            text = i18n.get_string(Gtk.Buildable.get_name(widget), lang)
            text = text.replace('${RELEASE}', release.name)
            widget.set_label(text)

    def on_nonfree_toggled(self, widget):
        enabled = self.get_use_nonfree()
        self.secureboot_box.set_sensitive(enabled)
        self.info_loop(None)

    def on_secureboot_toggled(self, widget):
        enabled = self.get_disable_secureboot()
        self.password_grid.set_sensitive(enabled)
        self.info_loop(None)

    def info_loop(self, unused_widget):
        if not self.get_use_nonfree() \
                or not self.password_grid.get_sensitive():
            self.controller.allow_go_forward(True)
            return True

        complete = False
        passw = self.password.get_text()
        vpassw = self.verified_password.get_text()

        if len(passw) == 0:
            self.password_strength.set_current_page(
                self.password_strength_pages['empty'])
        elif len(passw) >= 8:
            self.password_strength.set_current_page(
                self.password_strength_pages['good'])
        else:
            self.password_strength.set_current_page(
                self.password_strength_pages['too_short'])

        if len(passw) == 0 or len(vpassw) == 0:
            self.password_match.set_current_page(
                self.password_match_pages['empty'])
        elif passw != vpassw or (passw and len(passw) < 8):
            self.password_match.set_current_page(
                self.password_match_pages['empty'])
            if len(passw) >= 8 and (not passw.startswith(vpassw) or
                                    len(vpassw) / len(passw) > 0.6):
                self.password_match.set_current_page(
                    self.password_match_pages['mismatch'])
        else:
            complete = True
            self.password_match.set_current_page(
                self.password_match_pages['ok'])

        self.controller.allow_go_forward(complete)
        return complete

    def get_secureboot_key(self):
        return self.password.get_text()

    def show_learn_more(self, unused):
        from gi.repository import Gtk

        sb_title_template = 'lingmo_installer/text/efi_secureboot'
        sb_info_template = 'lingmo_installer/text/efi_secureboot_info'
        secureboot_title = self.controller.get_string(sb_title_template)
        secureboot_msg = self.controller.get_string(sb_info_template)

        dialog = Gtk.MessageDialog(
            self.current_page.get_toplevel(), Gtk.DialogFlags.MODAL,
            Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, None)
        dialog.set_title(secureboot_title)
        dialog.set_markup(secureboot_msg)
        dialog.run()
        dialog.destroy()


class PageKde(PreparePageBase):
    plugin_breadcrumb = 'lingmo_installer/text/breadcrumb_prepare'
    restricted_package_name = 'klingmo-restricted-addons'

    def __init__(self, controller, *args, **kwargs):
        from lingmo_installer.qtwidgets import StateBox
        self.controller = controller
        try:
            from PyQt5 import uic
            from PyQt5 import QtGui, QtWidgets
            # No worries, this has nothing to do with NM, we just want the
            # generic progress indicator from there
            from lingmo_installer.frontend.kde_components.nmwidgets import ProgressIndicator
            self.page = uic.loadUi('/usr/share/lingmo_installer/qt/stepPrepare.ui')
            self.prepare_minimal_install = self.page.prepare_minimal_install
            self.qt_label_minimal_install = self.page.qt_label_minimal_install
            self.prepare_download_updates = self.page.prepare_download_updates
            self.prepare_nonfree_software = self.page.prepare_nonfree_software
            self.prepare_foss_disclaimer = self.page.prepare_foss_disclaimer
            self.prepare_sufficient_space = StateBox(self.page)
            self.secureboot_label = self.page.secureboot_label
            self.disable_secureboot = self.page.disable_secureboot
            self.password = self.page.password
            self.verified_password = self.page.verified_password
            self.password_extra_label = self.page.password_extra_label
            self.badPassword = self.page.badPassword
            self.badPassword.setPixmap(QtGui.QPixmap(
                "/usr/share/icons/oxygen/16x16/status/dialog-warning.png"))
            self.progress_indicator = ProgressIndicator()
            self.progress_indicator.hide()
            layout = QtWidgets.QHBoxLayout(self.page.progress_container)
            layout.addWidget(self.progress_indicator)
            # TODO we should set these up and tear them down while on this
            # page.
            try:
                self.prepare_power_source = StateBox(self.page)
                if upower.has_battery():
                    upower.setup_power_watch(self.prepare_power_source)
                else:
                    self.prepare_power_source.hide()
            except Exception as e:
                # TODO use an inconsistent state?
                print('unable to set up power source watch:', e)
            if not os.path.exists(minimal_install_rlist_path):
                self.qt_label_minimal_install.hide()
                self.prepare_minimal_install.hide()
            try:
                self.prepare_network_connection = StateBox(self.page)
            except Exception as e:
                print('unable to set up network connection watch:', e)
        except Exception as e:
            print("Could not create prepare page:", str(e), file=sys.stderr)
            self.debug('Could not create prepare page: %s', e)
            self.page = None
        self.set_using_secureboot(False)
        self.plugin_widgets = self.page

    def show_rst_page(self):
        return False

    def show_lingmo_drivers_spinner(self):
        self.progress_indicator.show()
        self.progress_indicator.setSpinnerVisible(True)

    def hide_lingmo_drivers_spinner(self):
        self.progress_indicator.setSpinnerVisible(False)
        self.progress_indicator.hide()

    def plugin_on_next_clicked(self):
        if self.get_use_nonfree():
            self.show_lingmo_drivers_spinner()

    def show_insufficient_space_page(self, required, free):
        from PyQt5 import QtWidgets
        QtWidgets.QMessageBox.critical(self.page,
                                       free,
                                       required)
        sys.exit(1)
        return

    def set_using_secureboot(self, secureboot):
        self.using_secureboot = secureboot
        self.secureboot_label.setVisible(secureboot)
        self.disable_secureboot.setVisible(secureboot)
        self.password.setVisible(secureboot)
        self.verified_password.setVisible(secureboot)
        self.password_extra_label.setVisible(secureboot)
        self.badPassword.hide()
        if (secureboot):
            self.password.textChanged.connect(self.verify_password)
            self.verified_password.textChanged.connect(self.verify_password)

    # show warning if passwords do not match
    def verify_password(self):
        complete = False

        if self.password.text() == self.verified_password.text():
            self.badPassword.hide()
            complete = True
        else:
            self.badPassword.show()

        if not self.password.text():
            complete = False

        self.controller.allow_go_forward(complete)

    def get_secureboot_key(self):
        return str(self.page.password.text())

    def enable_download_updates(self, val):
        self.prepare_download_updates.setEnabled(val)

    def set_download_updates(self, val):
        self.prepare_download_updates.setChecked(val)

    def get_download_updates(self):
        from PyQt5.QtCore import Qt
        return self.prepare_download_updates.checkState() == Qt.Checked

    def set_minimal_install(self, val):
        self.prepare_minimal_install.setChecked(val)

    def get_minimal_install(self):
        if self.prepare_minimal_install.isChecked():
            return True
        return False

    def set_allow_nonfree(self, allow):
        if not allow:
            self.prepare_nonfree_software.setChecked(False)
            self.prepare_nonfree_software.setVisible(False)
            self.prepare_foss_disclaimer.setVisible(False)

    def set_use_nonfree(self, val):
        if osextras.find_on_path('lingmo-drivers'):
            self.prepare_nonfree_software.setChecked(val)
        else:
            self.debug('Could not find lingmo-drivers on the executable path.')
            self.set_allow_nonfree(False)

    def get_use_nonfree(self):
        from PyQt5.QtCore import Qt
        return self.prepare_nonfree_software.checkState() == Qt.Checked

    def plugin_translate(self, lang):
        PreparePageBase.plugin_translate(self, lang)
        # Translate the progress label
        self.progress_indicator.setText(self.controller.get_string(
            'lingmo_installer/text/preparing_ud_label', lang))
        # gtk does the ${RELEASE} replace for the title in gtk_ui but we do
        # it per plugin because our title widget is per plugin
        release = misc.get_release()
        widgets = (
            self.page.prepare_heading_label,
            self.page.prepare_download_updates,
        )
        for widget in widgets:
            text = widget.text()
            text = text.replace('${RELEASE}', release.name)
            text = text.replace('Lingmo', 'Klingmo')
            widget.setText(text)


class Page(plugin.Plugin):
    def prepare(self):
        if (self.db.get('apt-setup/restricted') == 'false' or
                self.db.get('apt-setup/multiverse') == 'false'):
            self.ui.set_allow_nonfree(False)
        else:
            use_nonfree = self.db.get('lingmo_installer/use_nonfree') == 'true'
            self.ui.set_use_nonfree(use_nonfree)

        arch, subarch = archdetect()
        if 'efi' in subarch:
            if is_secure_boot():
                self.ui.set_using_secureboot(True)

        self.ui.download_updates = self.db.get('lingmo_installer/download_updates') == 'true'
        if self.ui.download_updates_enabled:
            self.ui.set_download_updates(self.ui.download_updates)
        minimal_install = self.db.get('lingmo_installer/minimal_install') == 'true'
        self.ui.set_minimal_install(minimal_install)
        self.apply_debconf_branding()

        # wait for it to finish
        if self.frontend.lingmo_drivers:
            self.frontend.lingmo_drivers.communicate()
            self.frontend.lingmo_drivers = None

        # output whether there are OEM packages for this system
        try:
            with open('/run/lingmo-drivers-oem.autoinstall', 'r') as f:
                syslog.syslog(F'lingmo-drivers list-oem finished with: "{" ".join(f.read().splitlines())}"')
        except FileNotFoundError:
            syslog.syslog("lingmo-drivers list-oem finished with no available packages. Maybe we need to apt update? "
                          "Doing that and trying again.")
            # We only do this when we really have to since it could be slow: apt update & re-run of lingmo-drivers
            self.frontend.save_oem_metapackages_list(wait_finished=True)
            try:
                with open('/run/lingmo-drivers-oem.autoinstall', 'r') as f:
                    syslog.syslog(F'lingmo-drivers list-oem finished with: "{" ".join(f.read().splitlines())}"')
            except FileNotFoundError:
                syslog.syslog("No, we didn't find any OEM packages again.")

        if self.should_show_rst_page():
            if not self.ui.show_rst_page():
                self.setup_sufficient_space()
            else:
                self.ui.plugin_is_restart = True
        else:
            self.setup_sufficient_space()
        command = ['/usr/share/lingmo_installer/simple-plugins', 'prepare']
        questions = ['lingmo_installer/use_nonfree']
        return command, questions

    def apply_debconf_branding(self):
        release = misc.get_release()
        for template in ['lingmo_installer/text/required_space',
                         'lingmo_installer/text/free_space']:
            self.db.subst(template, 'RELEASE', release.name)

    def should_show_rst_page(self):
        search = '/sys/module/ahci/drivers/pci:ahci/*/remapped_nvme'
        for remapped_nvme in glob.glob(search):
            with open(remapped_nvme, 'r') as f:
                if int(f.read()) > 0:
                    return True
        return os.environ.get('SHOW_RST_UI', '0') == '1'

    def setup_sufficient_space(self):
        # TODO move into prepare.
        size = misc.install_size()
        self.db.subst(
            'lingmo_installer/text/required_space', 'SIZE',
            misc.format_size(size))
        free = self.free_space()
        self.db.subst(
            'lingmo_installer/text/free_space', 'SIZE',
            misc.format_size(free))
        required_text = self.description('lingmo_installer/text/required_space')
        free_text = self.description('lingmo_installer/text/free_space')
        self.ui.set_sufficient_space(size < free, required_text, free_text)

    def free_space(self):
        biggest = 0
        with misc.raised_privileges():
            proc = subprocess.Popen(
                ['parted_devices'],
                stdout=subprocess.PIPE, universal_newlines=True)
            devices = proc.communicate()[0].rstrip('\n').split('\n')
            for device in devices:
                if device and int(device.split('\t')[1]) > biggest:
                    biggest = int(device.split('\t')[1])
        return biggest

    def ok_handler(self):
        download_updates = self.ui.get_download_updates()
        minimal_install = self.ui.get_minimal_install()
        use_nonfree = self.ui.get_use_nonfree()
        secureboot_key = self.ui.get_secureboot_key()
        self.preseed_bool('lingmo_installer/use_nonfree', use_nonfree)
        self.preseed_bool('lingmo_installer/download_updates', download_updates)
        self.preseed_bool('lingmo_installer/minimal_install', minimal_install)
        if self.ui.using_secureboot and secureboot_key:
            self.preseed('lingmo_installer/secureboot_key', secureboot_key, seen=True)
        if use_nonfree:
            with misc.raised_privileges():
                # Install lingmo-restricted-addons.
                self.preseed_bool('apt-setup/universe', True)
                self.preseed_bool('apt-setup/multiverse', True)
                if self.db.fget('lingmo_installer/nonfree_package', 'seen') != 'true':
                    self.preseed(
                        'lingmo_installer/nonfree_package',
                        self.ui.restricted_package_name)
        plugin.Plugin.ok_handler(self)

    def cleanup(self):
        self.ui.hide_lingmo_drivers_spinner()
        plugin.Plugin.cleanup(self)
