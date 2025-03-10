#!/usr/bin/python3
# -*- coding: utf-8; -*-

import os
import unittest

import mock


class TestFrontend(unittest.TestCase):
    def setUp(self):
        for obj in ('lingmo_installer.misc.drop_privileges',
                    'lingmo_installer.misc.regain_privileges',
                    'lingmo_installer.misc.execute',
                    'lingmo_installer.misc.dmimodel',
                    'lingmo_installer.frontend.base.drop_privileges',
                    'lingmo_installer.frontend.gtk_ui.Wizard.customize_installer',
                    'lingmo_installer.nm.wireless_hardware_present',
                    'lingmo_installer.nm.NetworkManager.start',
                    'lingmo_installer.nm.NetworkManager.get_state',
                    'lingmo_installer.misc.has_connection',
                    'lingmo_installer.upower.setup_power_watch',
                    'dbus.mainloop.glib.DBusGMainLoop',
                    'lingmo_installer.i18n.reset_locale',
                    ):
            patcher = mock.patch(obj)
            patched_obj = patcher.start()
            self.addCleanup(patcher.stop)
            if obj in ('lingmo_installer.misc.wireless_hardware_present',
                       'lingmo_installer.misc.has_connection'):
                patched_obj.return_value = False
            elif obj == 'lingmo_installer.i18n.reset_locale':
                patched_obj.return_value = 'en_US.UTF-8'

    def test_question_dialog(self):
        from lingmo_installer.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-lingmo_installer')
        with mock.patch('gi.repository.Gtk.Dialog.run') as run:
            run.return_value = 0
            ret = ui.question_dialog(title='♥', msg='♥',
                                     options=('♥', '£'))
            self.assertEqual(ret, '£')
            run.return_value = 1
            ret = ui.question_dialog(title='♥', msg='♥',
                                     options=('♥', '£'))
            self.assertEqual(ret, '♥')

    # TODO: I'm not entirely sure this makes sense, but the numbers are
    # currently rather unstable and seem to depend quite a lot on the theme.
    # This may have something to do with pixmaps not being set up properly
    # when testing against a build tree.
    @unittest.skipIf('LINGMO-INSTALLER_TEST_INSTALLED' in os.environ,
                     'only testable against a build tree')
    def test_pages_fit_on_a_netbook(self):
        from lingmo_installer.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-lingmo_installer')
        ui.translate_pages()
        for page in ui.pages:
            ui.set_page(page.module.NAME)
            ui.refresh()
            ui.refresh()
            if 'LINGMO-INSTALLER_TEST_SHOW_ALL_PAGES' in os.environ:
                print(page.module.NAME)
                import time
                time.sleep(3)
            alloc = ui.live_installer.get_allocation()
            # width 640, because it is a common small 4:3 width
            # height 556, because e.g. HP Mini has 580 - 24px (indicators)
            # Anything smaller will need to use Alt+Ctrl+Pgd/Right
            # Scrollbars anyone?
            # self.assertLessEqual(alloc.width, 640, page.module.NAME)  # fixme
            self.assertLessEqual(alloc.height, 744, page.module.NAME)  # 768 - 24px (top panel)
            if page.module.NAME == 'partman':
                ui.allow_change_step(False)

    def test_interface_translated(self):
        import subprocess

        from gi.repository import Gtk

        from lingmo_installer.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-lingmo_installer')
        missing_translations = []
        with mock.patch.object(ui, 'translate_widget') as translate_widget:
            def side_effect(widget, lang=None, prefix=None):
                label = isinstance(widget, Gtk.Label)
                button = isinstance(widget, Gtk.Button)
                # We have some checkbuttons without labels.
                button = button and widget.get_label()
                # Stock buttons.
                window = isinstance(widget, Gtk.Window)
                if not (label or button or window):
                    return
                name = widget.get_name()
                if not ui.get_string(name, lang, prefix):
                    missing_translations.append(name)
            translate_widget.side_effect = side_effect
            ui.translate_widgets()
            whitelist = [
                # GTK-provided buttons with generic labels.
                'cancelbutton2', 'okbutton2', 'okbutton3',
                'partition_dialog_okbutton', 'cancelbutton3',
                'grub_fail_okbutton',
                'advanced_features_cancelbutton',
                'advanced_features_okbutton',
                # These are calculated and set as the partitioning options are
                # being calculated.
                'reuse_partition_desc', 'reuse_partition',
                'replace_partition_desc', 'replace_partition',
                'resize_use_free_desc', 'resize_use_free',
                'use_device_desc', 'use_device', 'part_ask_heading',
                'custom_partitioning_desc', 'custom_partitioning',
                'advanced_features_selected',
                # Pulled straight from debconf when the installation medium is
                # already mounted.
                'part_advanced_warning_message',
                # These are calculated and set inside info_loop in the user
                # setup page.
                'password_strength', 'hostname_error_label',
                'password_error_label', 'username_error_label',
                'recovery_strength',
                # Pulled straight from debconf into the UI on progress.
                'install_progress_text',
                # Contains just the traceback.
                'crash_detail_label',
                # Pages define a debconf template to look up and use as the
                # title. If it is not set or not found, the title is hidden.
                'page_title',
                # To be calculated and set
                'partition_lvm_status',
                'recovery_key_location',
                # These are "placeholders" for debconfs impromptu notices
                'ubi_question_dialog', 'question_label',
                # Calculated error string
                'label_global_error',
                'warning_password_label', 'label1', 'secureboot_label',
                # secure boot
                'disable_secureboot', 'prepare_foss_disclaimer',
                'label_free_space', 'label_required_space',
                'label_download_updates',
                # This one is set by either the wireless and prepare plugins
                # to indicate status
                'status_label',
            ]
            deb_host_arch = subprocess.Popen(
                ['dpkg-architecture', '-qDEB_HOST_ARCH'],
                stdout=subprocess.PIPE,
                universal_newlines=True).communicate()[0].strip()
            if deb_host_arch not in ('amd64', 'arm64', 'i386'):
                # grub-installer not available, but this template won't be
                # displayed anyway.
                whitelist.append('grub_device_label')
            missing_translations = set(missing_translations) - set(whitelist)
            missing_translations = list(missing_translations)
            if missing_translations:
                missing_translations = ', '.join(missing_translations)
                raise Exception('Missing translation for:\n%s'
                                % missing_translations)
