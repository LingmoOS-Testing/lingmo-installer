SUBDIRS = icons

@INTLTOOL_DESKTOP_RULE@

modedir = $(datadir)/gnome-shell/modes
mode_DATA = lingmo-installer.json

desktopdir = $(datadir)/applications
desktop_DATA = $(desktop_in_files:.desktop.in=.desktop)
desktop_in_files = \
	oem-config-prepare-gtk.desktop.in \
	oem-config-prepare-kde.desktop.in \
	lingmo-installer.desktop.in \
	lingmo-installer-kdeui.desktop.in

@INTLTOOL_POLICY_RULE@

polkit_policydir = $(datadir)/polkit-1/actions
polkit_policy_in_files = com.lingmo.lingmo-installer.policy.in
polkit_policy_DATA = $(polkit_policy_in_files:.policy.in=.policy)

EXTRA_DIST = $(desktop_in_files) $(polkit_policy_in_files) lingmo-installer.json

CLEANFILES = $(desktop_DATA)
