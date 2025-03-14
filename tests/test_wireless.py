#! /usr/bin/python3

import unittest

import mock

from lingmo_installer import nm, plugin_manager


class WirelessTests(unittest.TestCase):
    @mock.patch('lingmo_installer.nm.NetworkManager.start')
    @mock.patch('lingmo_installer.nm.NetworkManager.get_state')
    @mock.patch('lingmo_installer.misc.has_connection')
    def setUp(self, has_connection, get_state, *args):
        has_connection.return_value = True
        get_state.return_value = nm.NM_STATE_DISCONNECTED

        self.ubi_wireless = plugin_manager.load_plugin('ubi-wireless')

        self.gtk = self.ubi_wireless.PageGtk(mock.Mock())
        self.nmwidget = self.gtk.nmwidget
        self.manager = self.nmwidget.view.wifi_model
        self.model = self.manager.model
        self.manager.passphrases_cache = {}
