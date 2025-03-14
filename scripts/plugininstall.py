#!/usr/bin/python3
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005 Javier Carranza and others for Guadalinex
# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
# Copyright (C) 2007 Mario Limonciello
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
import grp
import gzip
import io
import itertools
import os
import platform
import pwd
import re
import shutil
import stat
import subprocess
import sys
import syslog
import textwrap
import traceback

import apt_pkg
from apt.cache import Cache, FetchFailedException
import debconf

sys.path.insert(0, '/usr/lib/lingmo_installer')

from lingmo_installer import install_misc, misc, osextras, plugin_manager
from lingmo_installer.components import apt_setup, check_kernels, hw_detect


HOSTS_TEXT = """\

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters"""


def cleanup_after(func):
    def wrapper(self):
        try:
            func(self)
        finally:
            self.cleanup()
            try:
                self.db.progress('STOP')
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                pass
    return wrapper


class PluginProgress:
    def __init__(self, db):
        self._db = db

    def info(self, title):
        self._db.progress('INFO', title)

    def get(self, question):
        return self._db.get(question)

    def substitute(self, template, substr, data):
        self._db.subst(template, substr, data)


class Install(install_misc.InstallBase):
    def __init__(self):
        install_misc.InstallBase.__init__(self)

        self.db = debconf.Debconf(
            read=io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8'),
            write=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8'))

        self.kernel_version = platform.release()
        self.re_kernel_version = re.compile(r'^linux-image-\d.*')

        # Get langpacks from install
        self.langpacks = []
        if os.path.exists('/var/lib/lingmo_installer/langpacks'):
            with open('/var/lib/lingmo_installer/langpacks') as langpacks:
                for line in langpacks:
                    self.langpacks.append(line.strip())

        # Load plugins
        modules = plugin_manager.load_plugins()
        modules = plugin_manager.order_plugins(modules)
        self.plugins = [x for x in modules if hasattr(x, 'Install')]

        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            self.target = '/'
            return

        apt_pkg.init_config()
        apt_pkg.config.set("Dir", self.target)
        apt_pkg.config.set("Dir::State::status",
                           self.target_file('var/lib/dpkg/status'))
        apt_pkg.config.set("APT::GPGV::TrustedKeyring",
                           self.target_file('etc/apt/trusted.gpg'))

        # Keep this in sync with configure_apt.
        # TODO cjwatson 2011-03-03: consolidate this.
        try:
            if self.db.get('base-installer/install-recommends') == 'false':
                apt_pkg.config.set("APT::Install-Recommends", "false")
        except debconf.DebconfError:
            pass
        apt_pkg.config.set("APT::Authentication::TrustCDROM", "true")
        apt_pkg.config.set("Acquire::gpgv::Options::",
                           "--ignore-time-conflict")
        try:
            if self.db.get('debian-installer/allow_unauthenticated') == 'true':
                apt_pkg.config.set("APT::Get::AllowUnauthenticated", "true")
                apt_pkg.config.set(
                    "Aptitude::CmdLine::Ignore-Trust-Violations", "true")
        except debconf.DebconfError:
            pass
        apt_pkg.config.set("APT::CDROM::NoMount", "true")
        apt_pkg.config.set("Acquire::cdrom::mount", "/cdrom")
        apt_pkg.config.set("Acquire::cdrom::/cdrom/::Mount", "true")
        apt_pkg.config.set("Acquire::cdrom::/cdrom/::UMount", "true")
        apt_pkg.config.set("Acquire::cdrom::AutoDetect", "false")
        apt_pkg.config.set("Dir::Media::MountPath", "/cdrom")

        apt_pkg.config.set("DPkg::Options::", "--root=%s" % self.target)
        # We don't want apt-listchanges or dpkg-preconfigure, so just clear
        # out the list of pre-installation hooks.
        apt_pkg.config.clear("DPkg::Pre-Install-Pkgs")
        apt_pkg.init_system()

        use_restricted = True
        try:
            if self.db.get('apt-setup/restricted') == 'false':
                use_restricted = False
        except debconf.DebconfError:
            pass
        if not use_restricted:
            self.restricted_cache = Cache()

    # TODO can we really pick up where install.py left off?  They're using two
    # separate databases, which means two progress states.  Might need to
    # record the progress position in find_next_step and pick up from there.
    # Ask Colin.
    @cleanup_after
    def run(self):
        """Main entry point."""
        # We pick up where install.py left off.
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            self.prev_count = 0
        else:
            self.prev_count = 74
        self.count = self.prev_count
        self.start = self.prev_count
        self.end = self.start + 22 + len(self.plugins)

        self.db.progress(
            'START', self.start, self.end, 'lingmo_installer/install/title')

        self.configure_python()

        self.next_region()
        self.db.progress('INFO', 'lingmo_installer/install/network')
        self.configure_network()

        self.configure_locale()

        self.next_region()
        self.db.progress('INFO', 'lingmo_installer/install/apt')
        self.configure_apt()

        self.configure_plugins()

        self.next_region()
        self.run_target_config_hooks()

        self.next_region(size=5)
        # Ignore failures from language pack installation.
        try:
            self.install_language_packs()
        except install_misc.InstallStepError:
            pass
        except IOError:
            pass
        except SystemError:
            pass

        self.next_region()
        self.remove_unusable_kernels()

        self.next_region(size=4)
        self.db.progress('INFO', 'lingmo_installer/install/hardware')
        self.configure_hardware()

        # Tell apt-install to install packages directly from now on.
        with open('/var/lib/lingmo_installer/apt-install-direct', 'w'):
            pass

        self.next_region()
        self.db.progress('INFO', 'lingmo_installer/install/installing')

        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            self.install_oem_extras()
        else:
            self.install_extras()

        # Configure zsys
        self.configure_zsys()

        self.next_region()
        self.db.progress('INFO', 'lingmo_installer/install/activedirectory')
        self.configure_active_directory()

        self.next_region()
        self.db.progress('INFO', 'lingmo_installer/install/bootloader')
        self.copy_mok()
        self.configure_recovery_key()
        self.configure_bootloader()

        self.next_region(size=4)
        self.db.progress('INFO', 'lingmo_installer/install/removing')
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            try:
                if misc.create_bool(self.db.get('oem-config/remove_extras')):
                    self.remove_oem_extras()
            except debconf.DebconfError:
                pass
        else:
            self.remove_extras()

        self.next_region()
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' not in os.environ:
            self.install_restricted_extras()

        try:
            self.copy_network_config()
        except Exception:
            syslog.syslog(
                syslog.LOG_WARNING,
                'Could not copy the network configuration:')
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_WARNING, line)
            self.db.input('critical', 'lingmo_installer/install/broken_network_copy')
            self.db.go()
        try:
            self.copy_bluetooth_config()
        except Exception:
            syslog.syslog(
                syslog.LOG_WARNING,
                'Could not copy the bluetooth configuration:')
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_WARNING, line)
            self.db.input('critical', 'lingmo_installer/install/broken_bluetooth_copy')
            self.db.go()
        try:
            self.recache_apparmor()
        except Exception:
            syslog.syslog(
                syslog.LOG_WARNING, 'Could not create an Apparmor cache:')
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_WARNING, line)
        try:
            self.copy_wallpaper_cache()
        except Exception:
            syslog.syslog(
                syslog.LOG_WARNING, 'Could not copy wallpaper cache:')
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_WARNING, line)
        self.copy_dcd()

        self.db.progress('SET', self.count)
        self.db.progress('INFO', 'lingmo_installer/install/log_files')
        self.copy_logs()
        self.save_random_seed()

        self.db.progress('SET', self.end)

    def _get_uid_gid_on_target(self, target_user):
        """Helper that gets the uid/gid of the username in the target chroot"""
        uid = subprocess.Popen(
            ['chroot', self.target, 'sudo', '-u', target_user, '--',
             'id', '-u'], stdout=subprocess.PIPE, universal_newlines=True)
        uid = uid.communicate()[0].strip('\n')
        gid = subprocess.Popen(
            ['chroot', self.target, 'sudo', '-u', target_user, '--',
             'id', '-g'], stdout=subprocess.PIPE, universal_newlines=True)
        gid = gid.communicate()[0].strip('\n')
        try:
            uid = int(uid)
            gid = int(gid)
        except ValueError:
            return (None, None)
        return uid, gid

    def configure_python(self):
        """Byte-compile Python modules.

        To save space, Lingmo excludes .pyc files from the live filesystem.
        Recreate them now to restore the appearance of a system installed
        from .debs.
        """
        cache = Cache()

        # Python standard library.
        re_minimal = re.compile(r'^python\d+\.\d+-minimal$')
        python_installed = sorted([
            pkg[:-8] for pkg in cache.keys()
            if re_minimal.match(pkg) and cache[pkg].is_installed])
        for python in python_installed:
            re_file = re.compile(r'^/usr/lib/%s/.*\.py$' % python)
            files = [
                f for f in cache['%s-minimal' % python].installed_files
                if (re_file.match(f) and
                    not os.path.exists(self.target_file('%sc' % f[1:])))]
            install_misc.chrex(self.target, python,
                               '/usr/lib/%s/py_compile.py' % python, *files)
            files = [
                f for f in cache[python].installed_files
                if (re_file.match(f) and
                    not os.path.exists(self.target_file('%sc' % f[1:])))]
            install_misc.chrex(self.target, python,
                               '/usr/lib/%s/py_compile.py' % python, *files)

        # Modules provided by the core Debian Python packages.
        default = subprocess.Popen(
            ['chroot', self.target, 'pyversions', '-d'],
            stdout=subprocess.PIPE,
            universal_newlines=True).communicate()[0].rstrip('\n')
        if default:
            install_misc.chrex(self.target, default, '-m', 'compileall',
                               '/usr/share/python/')
        if osextras.find_on_path_root(self.target, 'py3compile'):
            install_misc.chrex(self.target, 'py3compile', '-p', 'python3',
                               '/usr/share/python3/')

        def run_hooks(path, *args):
            for hook in osextras.glob_root(self.target, path):
                if not os.access(self.target_file(hook[1:]), os.X_OK):
                    continue
                install_misc.chrex(self.target, hook, *args)

        # Public and private modules provided by other packages.
        install_misc.chroot_setup(self.target)
        try:
            if osextras.find_on_path_root(self.target, 'pyversions'):
                supported = subprocess.Popen(
                    ['chroot', self.target, 'pyversions', '-s'],
                    stdout=subprocess.PIPE,
                    universal_newlines=True).communicate()[0].rstrip('\n')
                for python in supported.split():
                    try:
                        cachedpython = cache['%s-minimal' % python]
                    except KeyError:
                        continue
                    if not cachedpython.is_installed:
                        continue
                    version = cachedpython.installed.version
                    run_hooks('/usr/share/python/runtime.d/*.rtinstall',
                              'rtinstall', python, '', version)
                    run_hooks('/usr/share/python/runtime.d/*.rtupdate',
                              'pre-rtupdate', python, python)
                    run_hooks('/usr/share/python/runtime.d/*.rtupdate',
                              'rtupdate', python, python)
                    run_hooks('/usr/share/python/runtime.d/*.rtupdate',
                              'post-rtupdate', python, python)

            if osextras.find_on_path_root(self.target, 'py3versions'):
                supported = subprocess.Popen(
                    ['chroot', self.target, 'py3versions', '-s'],
                    stdout=subprocess.PIPE,
                    universal_newlines=True).communicate()[0].rstrip('\n')
                for python in supported.split():
                    try:
                        cachedpython = cache['%s-minimal' % python]
                    except KeyError:
                        continue
                    if not cachedpython.is_installed:
                        continue
                    version = cachedpython.installed.version
                    run_hooks('/usr/share/python3/runtime.d/*.rtinstall',
                              'rtinstall', python, '', version)
                    run_hooks('/usr/share/python3/runtime.d/*.rtupdate',
                              'pre-rtupdate', python, python)
                    run_hooks('/usr/share/python3/runtime.d/*.rtupdate',
                              'rtupdate', python, python)
                    run_hooks('/usr/share/python3/runtime.d/*.rtupdate',
                              'post-rtupdate', python, python)
        finally:
            install_misc.chroot_cleanup(self.target)

    def configure_network(self):
        """Automatically configure the network.

        At present, the only thing the user gets to tweak in the UI is the
        hostname. Some other things will be copied from the live filesystem,
        so changes made there will be reflected in the installed system.

        Unfortunately, at present we have to duplicate a fair bit of netcfg
        here, because it's hard to drive netcfg in a way that won't try to
        bring interfaces up and down.
        """
        # TODO cjwatson 2006-03-30: just call netcfg instead of doing all
        # this; requires a netcfg binary that doesn't bring interfaces up
        # and down

        if self.target != '/':
            for path in ('/etc/network/interfaces', '/etc/resolv.conf'):
                if os.path.exists(path):
                    targetpath = self.target_file(path[1:])
                    st = os.lstat(path)
                    if stat.S_ISLNK(st.st_mode):
                        if os.path.lexists(targetpath):
                            os.unlink(targetpath)
                        linkto = os.readlink(path)
                        os.symlink(linkto, targetpath)
                    else:
                        shutil.copy2(path, targetpath)

        try:
            hostname = self.db.get('netcfg/get_hostname')
        except debconf.DebconfError:
            hostname = ''
        try:
            domain = self.db.get('netcfg/get_domain').rstrip('.')
        except debconf.DebconfError:
            domain = ''
        if hostname == '':
            hostname = 'lingmo'

        with open(self.target_file('etc/hosts'), 'w') as hosts:
            print("127.0.0.1\tlocalhost", file=hosts)
            if domain:
                print("127.0.1.1\t%s.%s\t%s" % (hostname, domain, hostname),
                      file=hosts)
            else:
                print("127.0.1.1\t%s" % hostname, file=hosts)
            print(HOSTS_TEXT, file=hosts)

        # Network Manager's ifupdown plugin has an inotify watch on
        # /etc/hostname, which can trigger a race condition if /etc/hostname is
        # written and immediately followed with /etc/hosts.
        with open(self.target_file('etc/hostname'), 'w') as fp:
            print(hostname, file=fp)

        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            os.system("hostname %s" % hostname)

        persistent_net = '/etc/udev/rules.d/70-persistent-net.rules'
        if os.path.exists(persistent_net):
            if self.target != '/':
                shutil.copy2(
                    persistent_net, self.target_file(persistent_net[1:]))

    def run_plugin(self, plugin):
        """Run a single install plugin."""
        self.next_region()
        # set a generic info message in case plugin doesn't provide one
        self.db.progress('INFO', 'lingmo_installer/install/title')
        inst = plugin.Install(None, db=self.db)
        ret = inst.install(self.target, PluginProgress(self.db))
        if ret:
            raise install_misc.InstallStepError(
                "Plugin %s failed with code %s" % (plugin.NAME, ret))

    def configure_locale(self):
        """Configure the locale by running the language plugin.

        We need to do this as early as possible so that apt can emit
        properly-localised messages when running in the target system.
        """
        try:
            language_plugin = [
                plugin for plugin in self.plugins
                if (plugin_manager.get_mod_string(plugin, "NAME") ==
                    "language")][0]
        except IndexError:
            return
        self.run_plugin(language_plugin)
        # Don't run this plugin again.
        self.plugins = [
            plugin for plugin in self.plugins if plugin != language_plugin]

    def configure_plugins(self):
        """Apply plugin settings to installed system."""
        for plugin in self.plugins:
            self.run_plugin(plugin)

    def configure_apt(self):
        """Configure /etc/apt/sources.list."""
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return  # apt will already be setup as the OEM wants

        # TODO cjwatson 2007-07-06: Much of the following is
        # cloned-and-hacked from base-installer/debian/postinst. Perhaps we
        # should come up with a way to avoid this.

        # Keep this in sync with __init__.

        try:
            if self.db.get('base-installer/install-recommends') == 'false':
                tf = self.target_file('etc/apt/apt.conf.d/00InstallRecommends')
                with open(tf, 'w') as apt_conf_ir:
                    print('APT::Install-Recommends "false";', file=apt_conf_ir)
        except debconf.DebconfError:
            pass

        # Make apt trust CDs. This is not on by default (we think).
        # This will be left in place on the installed system.
        tf = self.target_file('etc/apt/apt.conf.d/00trustcdrom')
        with open(tf, 'w') as apt_conf_tc:
            print('APT::Authentication::TrustCDROM "true";', file=apt_conf_tc)

        # Avoid clock skew causing gpg verification issues.
        # This file will be left in place until the end of the install.
        tf = self.target_file('etc/apt/apt.conf.d/00IgnoreTimeConflict')
        with open(tf, 'w') as apt_conf_itc:
            print('Acquire::gpgv::Options { "--ignore-time-conflict"; };',
                  file=apt_conf_itc)

        try:
            if self.db.get('debian-installer/allow_unauthenticated') == 'true':
                tf = self.target_file(
                    'etc/apt/apt.conf.d/00AllowUnauthenticated')
                with open(tf, 'w') as apt_conf_au:
                    print('APT::Get::AllowUnauthenticated "true";',
                          file=apt_conf_au)
                    print('Aptitude::CmdLine::Ignore-Trust-Violations "true";',
                          file=apt_conf_au)
        except debconf.DebconfError:
            pass

        # let apt inside the chroot see the cdrom
        if self.target != "/":
            target_cdrom = self.target_file('cdrom')
            misc.execute('umount', target_cdrom)
            if not os.path.exists(target_cdrom):
                if os.path.lexists(target_cdrom):
                    os.unlink(target_cdrom)
                os.mkdir(target_cdrom)
            misc.execute('mount', '--bind', '/cdrom', target_cdrom)

        # Make apt-cdrom and apt not unmount/mount CD-ROMs.
        # This file will be left in place until the end of the install.
        tf = self.target_file('etc/apt/apt.conf.d/00NoMountCDROM')
        with open(tf, 'w') as apt_conf_nmc:
            print(textwrap.dedent("""\
                APT::CDROM::NoMount "true";
                Acquire::cdrom {
                  mount "/cdrom";
                  "/cdrom/" {
                    Mount  "true";
                    UMount "true";
                  };
                  AutoDetect "false";
                };
                Dir::Media::MountPath "/cdrom";"""), file=apt_conf_nmc)

        # This will be reindexed after installation based on the full
        # installed sources.list.
        try:
            shutil.rmtree(
                self.target_file('var/lib/apt-xapian-index'),
                ignore_errors=True)
        except OSError:
            pass

        dbfilter = apt_setup.AptSetup(None, self.db)
        ret = dbfilter.run_command(auto_process=True)
        if ret != 0:
            raise install_misc.InstallStepError(
                "AptSetup failed with code %d" % ret)

    def run_target_config_hooks(self):
        """Run hook scripts from /usr/lib/lingmo_installer/target-config.

        This allows live to hook into us and repeat bits of its
        configuration in the target system.
        """
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return  # These were already run once during install

        hookdir = '/usr/lib/lingmo_installer/target-config'

        if os.path.isdir(hookdir):
            # Exclude hooks containing '.', so that *.dpkg-* et al are avoided.
            hooks = [entry for entry in os.listdir(hookdir)
                     if '.' not in entry]
            self.db.progress('START', 0, len(hooks), 'lingmo_installer/install/title')
            self.db.progress('INFO', 'lingmo_installer/install/target_hooks')
            for hookentry in hooks:
                hook = os.path.join(hookdir, hookentry)
                syslog.syslog('running %s' % hook)
                if not os.access(hook, os.X_OK):
                    self.db.progress('STEP', 1)
                    continue
                # Errors are ignored at present, although this may change.
                subprocess.call(['log-output', '-t', 'lingmo_installer',
                                 '--pass-stdout', hook])
                self.db.progress('STEP', 1)
            self.db.progress('STOP')

    def install_language_packs(self):
        if not self.langpacks:
            return

        self.do_install(self.langpacks, langpacks=True)
        self.verify_language_packs()

    def verify_language_packs(self):
        if os.path.exists('/var/lib/lingmo_installer/no-install-langpacks'):
            return  # always complete enough

        if self.db.get('pkgsel/ignore-incomplete-language-support') == 'true':
            return

        cache = Cache()
        incomplete = False
        for pkg in self.langpacks:
            if pkg.startswith('gimp-help-'):
                # gimp-help-common is far too big to fit on CDs, so don't
                # worry about it.
                continue
            cachedpkg = install_misc.get_cache_pkg(cache, pkg)
            if cachedpkg is None or not cachedpkg.is_installed:
                syslog.syslog('incomplete language support: %s missing' % pkg)
                incomplete = True
                break
        if incomplete:
            language_support_dir = \
                self.target_file('usr/share/language-support')
            update_notifier_dir = \
                self.target_file('var/lib/update-notifier/user.d')
            for note in ('incomplete-language-support-gnome.note',
                         'incomplete-language-support-qt.note'):
                notepath = os.path.join(language_support_dir, note)
                if os.path.exists(notepath):
                    if not os.path.exists(update_notifier_dir):
                        os.makedirs(update_notifier_dir)
                    shutil.copy(notepath,
                                os.path.join(update_notifier_dir, note))
                    break

    def traverse_for_kernel(self, cache, pkg):
        kern = install_misc.get_cache_pkg(cache, pkg)
        if kern is None:
            return None
        pkc = cache._depcache.get_candidate_ver(kern._pkg)
        if 'Depends' in pkc.depends_list:
            dependencies = pkc.depends_list['Depends']
        else:
            # Didn't find.
            return None
        for dep in dependencies:
            name = dep[0].target_pkg.name
            if self.re_kernel_version.match(name):
                return name
            elif name.startswith('linux-'):
                return self.traverse_for_kernel(cache, name)

    def remove_unusable_kernels(self):
        """Remove unusable kernels.

        Keeping these may cause us to be unable to boot.
        """
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return

        self.db.progress('START', 0, 5, 'lingmo_installer/install/title')

        self.db.progress('INFO', 'lingmo_installer/install/find_removables')

        # Check for kernel packages to remove.
        dbfilter = check_kernels.CheckKernels(None, self.db)
        dbfilter.run_command(auto_process=True)

        install_kernels = set()
        new_kernel_pkg = None
        new_kernel_version = None
        install_kernels_path = "/var/lib/lingmo_installer/install-kernels"
        if os.path.exists(install_kernels_path):
            with open(install_kernels_path) as install_kernels_file:
                for line in install_kernels_file:
                    kernel = line.strip()
                    install_kernels.add(kernel)
                    # If we decided to actively install a particular kernel
                    # like this, it's probably because we prefer it to the
                    # default one, so we'd better update kernel_version to
                    # match.
                    if kernel.startswith('linux-image-2.'):
                        new_kernel_pkg = kernel
                        new_kernel_version = kernel[12:]
                    elif kernel.startswith('linux-'):
                        # Traverse dependencies to find the real kernel image.
                        cache = Cache()
                        kernel = self.traverse_for_kernel(cache, kernel)
                        if kernel:
                            new_kernel_pkg = kernel
                            new_kernel_version = kernel[12:]
            install_kernels_file.close()

        remove_kernels = set()
        remove_kernels_path = "/var/lib/lingmo_installer/remove-kernels"
        if os.path.exists(remove_kernels_path):
            with open(remove_kernels_path) as remove_kernels_file:
                for line in remove_kernels_file:
                    remove_kernels.add(line.strip())

        if len(install_kernels) == 0 and len(remove_kernels) == 0:
            self.db.progress('STOP')
            return

        # TODO cjwatson 2009-10-19: These regions are rather crude and
        # should be improved.
        self.db.progress('SET', 1)
        self.progress_region(1, 2)
        if install_kernels:
            self.do_install(install_kernels)
            install_misc.record_installed(install_kernels)
            if new_kernel_pkg:
                cache = Cache()
                cached_pkg = install_misc.get_cache_pkg(cache, new_kernel_pkg)
                if cached_pkg is not None and cached_pkg.is_installed:
                    self.kernel_version = new_kernel_version
                else:
                    remove_kernels = []
                del cache
            else:
                remove_kernels = []

        self.db.progress('SET', 2)
        self.progress_region(2, 5)
        try:
            if remove_kernels:
                install_misc.record_removed(remove_kernels, recursive=True)
        except Exception:
            self.db.progress('STOP')
            raise
        self.db.progress('SET', 5)
        self.db.progress('STOP')

    def configure_hardware(self):
        """Reconfigure several hardware-specific packages.

        These packages depend on the hardware of the system where the live
        filesystem was built, and must be reconfigured to work properly on
        the installed system.
        """
        self.nested_progress_start()
        install_misc.chroot_setup(self.target)
        try:
            dbfilter = hw_detect.HwDetect(None, self.db)
            ret = dbfilter.run_command(auto_process=True)
            if ret != 0:
                raise install_misc.InstallStepError(
                    "HwDetect failed with code %d" % ret)
        finally:
            install_misc.chroot_cleanup(self.target)
        self.nested_progress_end()

        self.db.progress('INFO', 'lingmo_installer/install/hardware')

        script = '/usr/lib/lingmo_installer/debian-installer-utils' \
                 '/register-module.post-base-installer'
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            script += '-oem'
        misc.execute(script)

        osextras.unlink_force(self.target_file('etc/papersize'))
        subprocess.call(['log-output', '-t', 'lingmo_installer', 'chroot', self.target,
                         'ucf', '--purge', '/etc/papersize'],
                        preexec_fn=install_misc.debconf_disconnect,
                        close_fds=True)
        try:
            install_misc.set_debconf(
                self.target, 'libpaper/defaultpaper', '', self.db)
        except debconf.DebconfError:
            pass

        osextras.unlink_force(
            self.target_file('etc/ssl/certs/ssl-cert-snakeoil.pem'))
        osextras.unlink_force(
            self.target_file('etc/ssl/private/ssl-cert-snakeoil.key'))

        # ensure /etc/mtab is a symlink
        osextras.unlink_force(self.target_file('etc/mtab'))
        os.symlink('../proc/self/mounts', self.target_file('etc/mtab'))

        install_misc.chroot_setup(self.target, x11=True)
        install_misc.chrex(
            self.target, 'dpkg-divert', '--package', 'lingmo_installer', '--rename',
            '--quiet', '--add', '/usr/sbin/update-initramfs')
        try:
            os.symlink(
                '/bin/true', self.target_file('usr/sbin/update-initramfs'))
        except OSError:
            pass

        packages = ['linux-image-' + self.kernel_version,
                    'libpaper1',
                    'ssl-cert']
        arch, subarch = install_misc.archdetect()

        try:
            for package in packages:
                install_misc.reconfigure(self.target, package)
        finally:
            osextras.unlink_force(
                self.target_file('usr/sbin/update-initramfs'))
            install_misc.chrex(
                self.target, 'dpkg-divert', '--package', 'lingmo_installer',
                '--rename', '--quiet', '--remove',
                '/usr/sbin/update-initramfs')
            install_misc.chrex(
                self.target, 'update-initramfs', '-c',
                '-k', self.kernel_version)
            install_misc.chroot_cleanup(self.target, x11=True)

        # Fix up kernel symlinks now that the initrd exists. Depending on
        # the architecture, these may be in / or in /boot.
        bootdir = self.target_file('boot')
        if self.db.get('base-installer/kernel/linux/link_in_boot') == 'true':
            linkdir = bootdir
            linkprefix = ''
        else:
            linkdir = self.target
            linkprefix = 'boot'

        # Remove old symlinks. We'll set them up from scratch.
        re_symlink = re.compile('vmlinu[xz]|initrd.img$')
        for entry in os.listdir(linkdir):
            if re_symlink.match(entry) is not None:
                filename = os.path.join(linkdir, entry)
                if os.path.islink(filename):
                    os.unlink(filename)
        if linkdir != self.target:
            # Remove symlinks in /target too, which may have been created on
            # the live filesystem. This isn't necessary, but it may help
            # avoid confusion.
            for entry in os.listdir(self.target):
                if re_symlink.match(entry) is not None:
                    filename = self.target_file(entry)
                    if os.path.islink(filename):
                        os.unlink(filename)

        # Create symlinks. Prefer our current kernel version if possible,
        # but if not (perhaps due to a customised live filesystem image),
        # it's better to create some symlinks than none at all.
        re_image = re.compile('(vmlinu[xz]|initrd.img)-')
        for entry in os.listdir(bootdir):
            match = re_image.match(entry)
            if match is not None:
                imagetype = match.group(1)
                linksrc = os.path.join(linkprefix, entry)
                linkdst = os.path.join(linkdir, imagetype)
                if os.path.exists(linkdst):
                    if entry.endswith('-' + self.kernel_version):
                        os.unlink(linkdst)
                    else:
                        continue
                os.symlink(linksrc, linkdst)

    def configure_recovery_key(self):
        crypto_key = self.db.get('lingmo_installer/crypto_key')
        recovery_key = self.db.get('lingmo_installer/recovery_key')
        if not crypto_key or not recovery_key:
            self.clean_crypto_keys()
            return

        debconf_disk = self.db.get('partman-auto/select_disk')
        disk = debconf_disk.split('/')[-1].replace('=', '/')
        if not disk:  # disk is not set in manual partitioning mode
            syslog.syslog(
                syslog.LOG_ERR,
                'Determining installation disk failed. '
                'Setting a recovery key is supported only with partman-auto.')
            self.clean_crypto_keys()
            self.db.input('critical', 'lingmo_installer/install/broken_luks_add_key')
            self.db.go()
            return

        args = ['lsblk', '-lp', '-oNAME,FSTYPE', disk]
        lsblk_out = subprocess.check_output(args).decode(sys.stdout.encoding)
        for line in lsblk_out.splitlines():
            if 'crypto_LUKS' not in line:
                continue
            dev = line.split()[0]

        if not dev:
            syslog.syslog(syslog.LOG_ERR, ' '.join(args))
            syslog.syslog(syslog.LOG_ERR, 'determining crypto device failed. Output: %s' % lsblk_out)
            self.clean_crypto_keys()
            self.db.input('critical', 'lingmo_installer/install/broken_luks_add_key')
            self.db.go()
            return
        syslog.syslog(' '.join(args))

        key_args = "%s\n%s" % (crypto_key, recovery_key)
        try:
            log_args = ['log-output', '-t', 'lingmo_installer']
            log_args.extend(['cryptsetup', 'luksAddKey', dev])
            p = subprocess.run(log_args, input=key_args, encoding="utf-8")
        except subprocess.CalledProcessError as e:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            syslog.syslog(syslog.LOG_ERR, "cryptsetup failed(%s): %s" % (e.returncode, e.output))
            return
        finally:
            self.clean_crypto_keys()

        if p.returncode != 0:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            self.db.input('critical', 'lingmo_installer/install/broken_luks_add_key')
            self.db.go()
            return

        syslog.syslog(' '.join(log_args))

    def clean_crypto_keys(self):
        self.db.set('lingmo_installer/crypto_key', '')
        self.db.set('lingmo_installer/recovery_key', '')

    def configure_bootloader(self):
        """Configure and install the boot loader."""
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            # the language might be different than initial install.
            # recopy translations if we have them now
            full_lang = self.db.get('debian-installer/locale').split('.')[0]
            for lang in [full_lang.split('.')[0], full_lang.split('_')[0]]:
                source = (
                    '/usr/share/locale-langpack/%s/LC_MESSAGES/grub.mo' % lang)
                if (os.path.exists(source) and
                        os.path.isdir('/boot/grub/locale')):
                    shutil.copy(source, '/boot/grub/locale/%s.mo' % lang)
                    break
            return

        inst_boot = self.db.get('lingmo_installer/install_bootloader')
        if inst_boot == 'true' and 'LINGMO-INSTALLER_NO_BOOTLOADER' not in os.environ:
            binds = ("/proc", "/sys", "/dev", "/run",
                     "/sys/firmware/efi/efivars")
            for bind in binds:
                misc.execute('mount', '--bind', bind, self.target + bind)

            arch, subarch = install_misc.archdetect()

            try:
                if arch in ('amd64', 'arm64', 'i386'):
                    from lingmo_installer.components import grubinstaller
                    while 1:
                        dbfilter = grubinstaller.GrubInstaller(None, self.db)
                        ret = dbfilter.run_command(auto_process=True)
                        if subarch == 'efi' and ret != 0:
                            raise install_misc.InstallStepError(
                                "GrubInstaller failed with code %d" % ret)
                        elif ret != 0:
                            old_bootdev = self.db.get('grub-installer/bootdev')
                            bootdev = 'lingmo_installer/install/new-bootdev'
                            self.db.fset(bootdev, 'seen', 'false')
                            self.db.set(bootdev, old_bootdev)
                            self.db.input('critical', bootdev)
                            self.db.go()
                            response = self.db.get(bootdev)
                            if response == 'skip':
                                break
                            if not response:
                                raise install_misc.InstallStepError(
                                    "GrubInstaller failed with code %d" % ret)
                            else:
                                self.db.set('grub-installer/bootdev', response)
                        else:
                            break
                    if arch == 'amd64' and subarch != 'efi' and os.path.ismount("/target/boot/efi"):
                        dbfilter = grubinstaller.GrubInstaller(
                            None, self.db, extra_args=['amd64/efi'])
                        ret = dbfilter.run_command(auto_process=True)
                        if ret != 0:
                            raise install_misc.InstallStepError(
                                "GrubInstaller failed with code %d" % ret)
                else:
                    raise install_misc.InstallStepError(
                        "No bootloader installer found")
            except ImportError:
                raise install_misc.InstallStepError(
                    "No bootloader installer found")

            for bind in binds:
                misc.execute('umount', '-f', self.target + bind)

    def configure_zsys(self):
        """ Configure zsys """
        use_zfs = self.db.get('lingmo_installer/use_zfs')
        if use_zfs:
            misc.execute_root('/usr/share/lingmo_installer/zsys-setup', 'finalize')

    def configure_active_directory(self):
        """ Join Active Directory domain and enable pam_mkhomedir """
        use_directory = self.db.get('lingmo_installer/login_use_directory')
        if use_directory != 'true':
            install_misc.record_removed(['adcli', 'realmd', 'sssd'], recursive=True)
            return

        from socket import gethostname
        hostname_cur = gethostname()
        hostname_new = ''
        with open(self.target_file('etc/hostname'), 'r') as f:
            hostname_new = f.read().strip()

        # Set hostname for AD to determine FQDN (no fqdn option in realm join, only adcli)
        misc.execute_root('hostname', hostname_new)

        directory_domain = self.db.get('lingmo_installer/directory_domain')
        directory_user = self.db.get('lingmo_installer/directory_user')
        directory_passwd = self.db.get('lingmo_installer/directory_passwd')

        binds = ("/proc", "/sys", "/dev", "/run")
        try:
            for bind in binds:
                misc.execute('mount', '--bind', bind, self.target + bind)
            # join AD on host (services are running on host)
            if not self.join_domain(hostname_new, directory_domain, directory_user, directory_passwd):
                self.db.input('critical', 'lingmo_installer/install/broken_active_directory')
                self.db.go()
            install_misc.record_removed(['adcli'], recursive=True)
        finally:
            for bind in binds:
                misc.execute('umount', '-f', self.target + bind)
            # Reset hostname
            misc.execute_root('hostname', hostname_cur)

        # Enable pam_mkhomedir
        try:
            subprocess.check_call(['chroot', self.target, 'pam-auth-update',
                                   '--package', '--enable', 'mkhomedir'],
                                  preexec_fn=install_misc.debconf_disconnect)
        except subprocess.CalledProcessError:
            self.db.input('critical', 'lingmo_installer/install/broken_active_directory')
            self.db.go()

    def join_domain(self, hostname, directory_domain, directory_user, directory_passwd):
        """ Join an Active Directory domain """
        log_args = ['log-output', '-t', 'lingmo_installer']
        log_args.extend(['realm', 'join', '--install', self.target,
                         '--user', directory_user, '--computer-name', hostname,
                         '--unattended', directory_domain])
        try:
            p = subprocess.run(log_args, input=directory_passwd, timeout=60, encoding="utf-8")
        except TimeoutError as e:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            syslog.syslog(syslog.LOG_ERR, "Command timed out(%s): %s" % (e.errno, e.strerror))
            return False
        except IOError as e:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            syslog.syslog(syslog.LOG_ERR, "OS error(%s): %s" % (e.errno, e.strerror))
            return False

        if p.returncode != 0:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            return False

        syslog.syslog(' '.join(log_args))
        return True

    def copy_mok(self):
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return
        try:
            if self.db.get('oem-config/enable') == 'true':
                return
        except debconf.DebconfError:
            pass

        source = "/var/lib/shim-signed/mok/"
        target = "/target/var/lib/shim-signed/mok/"

        if not os.path.exists(source):
            return

        os.makedirs(target, exist_ok=True)
        for mok_file in os.listdir(source):
            source_file = os.path.join(source, mok_file)
            target_file = os.path.join(target, mok_file)

            if os.path.exists(target_file):
                continue

            shutil.copy(source_file, target_file)

    def do_remove(self, to_remove, recursive=False):
        self.nested_progress_start()

        self.db.progress('START', 0, 5, 'lingmo_installer/install/title')
        self.db.progress('INFO', 'lingmo_installer/install/find_removables')

        fetchprogress = install_misc.DebconfAcquireProgress(
            self.db, 'lingmo_installer/install/title',
            'lingmo_installer/install/apt_indices_starting',
            'lingmo_installer/install/apt_indices')
        cache = Cache()

        if cache._depcache.broken_count > 0:
            syslog.syslog(
                'not processing removals, since there are broken packages: '
                '%s' % ', '.join(install_misc.broken_packages(cache)))
            self.db.progress('STOP')
            self.nested_progress_end()
            return

        with cache.actiongroup():
            install_misc.get_remove_list(cache, to_remove, recursive)

        with cache.actiongroup():
            for cachedpkg in cache:
                if cachedpkg.is_auto_removable and not cachedpkg.marked_delete:
                    syslog.syslog("Autopurge %s" % cachedpkg.name)
                    cachedpkg.mark_delete(auto_fix=False, purge=True)

        self.db.progress('SET', 1)
        self.progress_region(1, 5)
        fetchprogress = install_misc.DebconfAcquireProgress(
            self.db, 'lingmo_installer/install/title', None,
            'lingmo_installer/install/fetch_remove')
        installprogress = install_misc.DebconfInstallProgress(
            self.db, 'lingmo_installer/install/title', 'lingmo_installer/install/apt_info',
            'lingmo_installer/install/apt_error_remove')
        install_misc.chroot_setup(self.target)
        commit_error = None
        try:
            try:
                if not cache.commit(fetchprogress, installprogress):
                    fetchprogress.stop()
                    installprogress.finish_update()
                    self.db.progress('STOP')
                    self.nested_progress_end()
                    return
            except SystemError as e:
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                commit_error = str(e)
        finally:
            install_misc.chroot_cleanup(self.target)
        self.db.progress('SET', 5)

        cache.open(None)
        if commit_error or cache._depcache.broken_count > 0:
            if commit_error is None:
                commit_error = ''
            brokenpkgs = install_misc.broken_packages(cache)
            syslog.syslog('broken packages after removal: '
                          '%s' % ', '.join(brokenpkgs))
            self.db.subst('lingmo_installer/install/broken_remove', 'ERROR',
                          commit_error)
            self.db.subst('lingmo_installer/install/broken_remove', 'PACKAGES',
                          ', '.join(brokenpkgs))
            self.db.input('critical', 'lingmo_installer/install/broken_remove')
            self.db.go()

        self.db.progress('STOP')

        self.nested_progress_end()

    def install_oem_extras(self):
        """Try to install additional packages requested by the distributor."""
        try:
            inst_langpacks = \
                self.db.get('oem-config/install-language-support') == 'true'
        except debconf.DebconfError:
            inst_langpacks = False
        if inst_langpacks:
            self.select_language_packs()
            recorded = install_misc.query_recorded_installed()

        try:
            extra_packages = self.db.get('oem-config/extra_packages')
            if extra_packages:
                extra_packages = extra_packages.replace(',', ' ').split()
            elif not inst_langpacks:
                return
            else:
                extra_packages = []
        except debconf.DebconfError:
            if not inst_langpacks:
                return

        if inst_langpacks:
            extra_packages += recorded

        save_replace = None
        save_override = None
        custom = '/etc/apt/sources.list.d/oem-config.list'
        apt_update = ['debconf-apt-progress', '--', 'apt-get', 'update']
        trusted_db = '/etc/apt/trusted.gpg'
        try:
            if 'DEBCONF_DB_REPLACE' in os.environ:
                save_replace = os.environ['DEBCONF_DB_REPLACE']
            if 'DEBCONF_DB_OVERRIDE' in os.environ:
                save_override = os.environ['DEBCONF_DB_OVERRIDE']
            os.environ['DEBCONF_DB_REPLACE'] = 'configdb'
            os.environ['DEBCONF_DB_OVERRIDE'] = 'Pipe{infd:none outfd:none}'

            try:
                extra_pool = self.db.get('oem-config/repository')
            except debconf.DebconfError:
                extra_pool = ''
            try:
                extra_key = self.db.get('oem-config/key')
            except debconf.DebconfError:
                extra_key = ''

            if extra_pool:
                with open(custom, 'w') as f:
                    print(extra_pool, file=f)
            if extra_key and os.path.exists(extra_key):
                if os.path.exists(trusted_db):
                    shutil.copy(trusted_db, trusted_db + '.oem-config')
                subprocess.call(['apt-key', 'add', extra_key])
            if extra_pool:
                subprocess.call(apt_update)
            # We don't support asking questions on behalf of packages specified
            # here yet, as we don't support asking arbitrary questions in
            # components/install.py yet.  This is complicated not only by the
            # present lack of dialogs for string and multiselect, but also
            # because we don't have any way of discerning between questions
            # asked by this module and questions asked by packages being
            # installed.
            cmd = ['debconf-apt-progress', '--', 'apt-get', '-y', 'install']
            cmd += extra_packages
            try:
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as e:
                if e.returncode != 30:
                    cache = Cache()
                    brokenpkgs = install_misc.broken_packages(cache)
                    self.warn_broken_packages(brokenpkgs, str(e))
        finally:
            if os.path.exists(trusted_db + '.oem-config'):
                shutil.copy(trusted_db + '.oem-config', trusted_db)
            if os.path.exists(custom):
                os.unlink(custom)
                subprocess.call(apt_update)
            if save_replace:
                os.environ['DEBCONF_DB_REPLACE'] = save_replace
            if save_override:
                os.environ['DEBCONF_DB_OVERRIDE'] = save_override

        if inst_langpacks:
            self.verify_language_packs()

    def install_restricted_extras(self):
        packages = []
        if self.db.get('lingmo_installer/use_nonfree') == 'true':
            self.db.progress('INFO', 'lingmo_installer/install/nonfree')
            packages.extend(self.db.get('lingmo_installer/nonfree_package').split())
        # also install recorded non-free packages
        packages.extend(install_misc.query_recorded_installed())
        self.do_install(packages)

    def install_extras(self):
        """Try to install packages requested by installer components."""
        # We only ever install these packages from the CD.
        sources_list = self.target_file('etc/apt/sources.list')
        os.rename(sources_list, "%s.apt-setup" % sources_list)
        with open("%s.apt-setup" % sources_list) as old_sources:
            with open(sources_list, 'w') as new_sources:
                found_cdrom = False
                for line in old_sources:
                    if 'cdrom:' in line:
                        print(line, end="", file=new_sources)
                        found_cdrom = True
        if not found_cdrom:
            os.rename("%s.apt-setup" % sources_list, sources_list)

        # this will install free & non-free things, but not things
        # that have multiarch Depends or Recommends. Instead, those
        # will be installed by install_restricted_extras() later
        # because this function runs before i386 foreign arch is
        # enabled
        cache = Cache()
        filtered_extra_packages = install_misc.query_recorded_installed()
        for package in sorted(filtered_extra_packages):
            pkg = cache.get(package)
            if not pkg:
                continue
            candidate = pkg.candidate
            dependencies = candidate.dependencies + candidate.recommends
            all_deps = itertools.chain.from_iterable(dependencies)
            for dep in all_deps:
                if ':' in dep.name:
                    filtered_extra_packages.remove(package)
                    break

        # An ordered list from the set() to avoid the random dependencies failure.
        self.do_install(sorted(filtered_extra_packages))

        if self.db.get('lingmo_installer/install_oem') == 'true':
            try:
                # If we installed any OEM metapackages, we should try to update /
                # upgrade them to their versions in the OEM archive.
                with open('/run/lingmo-drivers-oem.autoinstall', 'r') as f:
                    oem_pkgs = set(f.read().splitlines())
                    for oem_pkg in sorted(oem_pkgs):
                        target_sources_list = self.target_file("etc/apt/sources.list.d/{}.list".format(oem_pkg))
                        if not os.path.exists(target_sources_list):
                            continue

                        try:
                            cache.update(sources_list=target_sources_list)
                            cache.open()
                        except FetchFailedException:
                            syslog.syslog("Failed to apt update {}".format(target_sources_list))
                            oem_pkgs.discard(oem_pkg)
                    if oem_pkgs:
                        # An ordered list from the set() to avoid the random dependencies failure.
                        self.do_install(sorted(oem_pkgs))
            except FileNotFoundError:
                pass

        if found_cdrom:
            os.rename("%s.apt-setup" % sources_list, sources_list)

        # TODO cjwatson 2007-08-09: python reimplementation of
        # oem-config/finish-install.d/07oem-config-user. This really needs
        # to die in a great big chemical fire and call the same shell script
        # instead.
        try:
            if self.db.get('oem-config/enable') == 'true':
                if os.path.isdir(self.target_file('home/oem')):
                    with open(self.target_file('home/oem/.hwdb'), 'w'):
                        pass

                    apps_dir = 'usr/share/applications'
                    for desktop_file in (
                            apps_dir + '/oem-config-prepare-gtk.desktop',
                            apps_dir + '/kde/oem-config-prepare-kde.desktop'):
                        if os.path.exists(self.target_file(desktop_file)):
                            desktop_base = os.path.basename(desktop_file)
                            install_misc.chrex(
                                self.target, 'install', '-d',
                                '-o', 'oem', '-g', 'oem',
                                '/home/oem/Desktop')
                            install_misc.chrex(
                                self.target, 'install',
                                '-o', 'oem', '-g', 'oem',
                                '/%s' % desktop_file,
                                '/home/oem/Desktop/%s' % desktop_base)
                            install_misc.chrex(
                                self.target,
                                'sudo', '-i', '-u', 'oem',
                                'dbus-run-session', '--',
                                'gio', 'set',
                                '/home/oem/Desktop/%s' % desktop_base,
                                'metadata::trusted', 'true')
                            break

                    # Disable gnome-initial-setup for the OEM user
                    install_misc.chrex(
                        self.target, 'install', '-d',
                        '-o', 'oem', '-g', 'oem',
                        '/home/oem/.config')
                    install_misc.chrex(
                        self.target,
                        'sudo', '-i', '-u', 'oem',
                        'touch', '/home/oem/.config/gnome-initial-setup-done')

                # Carry the locale setting over to the installed system.
                # This mimics the behavior in 01oem-config-udeb.
                di_locale = self.db.get('debian-installer/locale')
                if di_locale:
                    install_misc.set_debconf(
                        self.target, 'debian-installer/locale', di_locale,
                        self.db)
                # in an automated install, this key needs to carry over
                installable_lang = self.db.get(
                    'lingmo_installer/only-show-installable-languages')
                if installable_lang:
                    install_misc.set_debconf(
                        self.target,
                        'lingmo_installer/only-show-installable-languages',
                        installable_lang, self.db)
        except debconf.DebconfError:
            pass

    def remove_oem_extras(self):
        """Remove unnecessary packages in OEM mode.

        Try to remove packages that were not part of the base install and
        are not needed by the final system.

        This is roughly the set of packages installed by lingmo_installer + packages
        we explicitly installed in oem-config (langpacks, for example) -
        everything else.
        """
        manifest = '/var/lib/lingmo_installer/installed-packages'
        if not os.path.exists(manifest):
            return

        keep = set()
        with open(manifest) as manifest_file:
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    keep.add(line.split()[0])
        # Let's not rip out the ground beneath our feet.
        keep.add('lingmo_installer')
        keep.add('oem-config')

        cache = Cache()
        # TODO cjwatson 2012-05-04: It would be nice to use a set
        # comprehension here, but that causes:
        #   SyntaxError: can not delete variable 'cache' referenced in nested
        #   scope
        remove = set([pkg for pkg in cache.keys() if cache[pkg].is_installed])
        # Keep packages we explicitly installed.
        keep |= install_misc.query_recorded_installed()
        remove -= install_misc.expand_dependencies_simple(cache, keep, remove)
        del cache

        install_misc.record_removed(remove)
        (regular, recursive) = install_misc.query_recorded_removed()
        self.do_remove(regular)
        self.do_remove(recursive, recursive=True)

    def copy_tree(self, source, target, uid, gid):
        # Mostly stolen from copy_all.
        directory_times = []
        s = '/'
        for p in target.split(os.sep)[1:]:
            s = os.path.join(s, p)
            if not os.path.exists(s):
                os.mkdir(s)
                os.lchown(s, uid, gid)
        for dirpath, dirnames, filenames in os.walk(source):
            sp = dirpath[len(source) + 1:]
            for name in dirnames + filenames:
                relpath = os.path.join(sp, name)
                sourcepath = os.path.join(source, relpath)
                targetpath = os.path.join(target, relpath)
                st = os.lstat(sourcepath)

                # Remove the target if necessary and if we can.
                install_misc.remove_target(source, target, relpath, st)

                # Now actually copy source to target.
                mode = stat.S_IMODE(st.st_mode)
                if stat.S_ISLNK(st.st_mode):
                    linkto = os.readlink(sourcepath)
                    os.symlink(linkto, targetpath)
                elif stat.S_ISDIR(st.st_mode):
                    if not os.path.isdir(targetpath):
                        os.mkdir(targetpath, mode)
                elif stat.S_ISCHR(st.st_mode):
                    os.mknod(targetpath, stat.S_IFCHR | mode, st.st_rdev)
                elif stat.S_ISBLK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFBLK | mode, st.st_rdev)
                elif stat.S_ISFIFO(st.st_mode):
                    os.mknod(targetpath, stat.S_IFIFO | mode)
                elif stat.S_ISSOCK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFSOCK | mode)
                elif stat.S_ISREG(st.st_mode):
                    install_misc.copy_file(
                        self.db, sourcepath, targetpath, True)

                os.lchown(targetpath, uid, gid)
                if not stat.S_ISLNK(st.st_mode):
                    os.chmod(targetpath, mode)
                if stat.S_ISDIR(st.st_mode):
                    directory_times.append(
                        (targetpath, st.st_atime, st.st_mtime))
                # os.utime() sets timestamp of target, not link
                elif not stat.S_ISLNK(st.st_mode):
                    try:
                        os.utime(targetpath, (st.st_atime, st.st_mtime))
                    except Exception:
                        # We can live with timestamps being wrong.
                        pass

        # Apply timestamps to all directories now that the items within them
        # have been copied.
        for dirtime in directory_times:
            (directory, atime, mtime) = dirtime
            try:
                os.utime(directory, (atime, mtime))
            except Exception:
                # I have no idea why I've been getting lots of bug reports
                # about this failing, but I really don't care. Ignore it.
                pass

    def remove_extras(self):
        """Remove unnecessary packages.

        Try to remove packages that are needed on the live CD but not on the
        installed system.
        """
        # Looking through files for packages to remove is pretty quick, so
        # don't bother with a progress bar for that.

        # Check for packages specific to the live CD.  (manifest-desktop is
        # the old method, which listed all the packages to keep;
        # manifest-remove is the new method, which lists all the packages to
        # remove.)
        manifest_remove = os.path.join(self.live_path,
                                       'filesystem.manifest-remove')
        manifest_desktop = os.path.join(self.live_path,
                                        'filesystem.manifest-desktop')
        manifest = os.path.join(self.live_path, 'filesystem.manifest')
        if os.path.exists(manifest_remove) and os.path.exists(manifest):
            difference = set()
            with open(manifest_remove) as manifest_file:
                for line in manifest_file:
                    if line.strip() != '' and not line.startswith('#'):
                        pkg = line.split(':')[0]
                        difference.add(pkg.split()[0])
            live_packages = set()
            with open(manifest) as manifest_file:
                for line in manifest_file:
                    if line.strip() != '' and not line.startswith('#'):
                        pkg = line.split(':')[0]
                        live_packages.add(pkg.split()[0])
            desktop_packages = live_packages - difference
        elif os.path.exists(manifest_desktop) and os.path.exists(manifest):
            desktop_packages = set()
            with open(manifest_desktop) as manifest_file:
                for line in manifest_file:
                    if line.strip() != '' and not line.startswith('#'):
                        pkg = line.split(':')[0]
                        desktop_packages.add(pkg.split()[0])
            live_packages = set()
            with open(manifest) as manifest_file:
                for line in manifest_file:
                    if line.strip() != '' and not line.startswith('#'):
                        pkg = line.split(':')[0]
                        live_packages.add(pkg.split()[0])
            difference = live_packages - desktop_packages
        else:
            difference = set()

        # Add minimal installation package list if selected
        if self.db.get('lingmo_installer/minimal_install') == 'true':
            if os.path.exists(install_misc.minimal_install_rlist_path):
                rm = set()
                with open(install_misc.minimal_install_rlist_path) as m_file:
                    rm = {line.strip().split(':')[0] for line in m_file}
                difference |= rm

        # Keep packages we explicitly installed.
        keep = install_misc.query_recorded_installed()

        arch, subarch = install_misc.archdetect()

        if arch in ('amd64', 'arm64', 'i386'):
            for pkg in ('grub', 'grub-efi', 'grub-efi-amd64',
                        'grub-efi-arm64', 'grub-efi-arm64-signed',
                        'flash-kernel', 'aarch64-laptops-support',
                        'grub-efi-amd64-signed', 'shim-signed', 'mokutil',
                        'lilo'):
                if pkg not in keep:
                    difference.add(pkg)

        cache = Cache()
        difference -= install_misc.expand_dependencies_simple(
            cache, keep, difference)
        del cache

        if len(difference) == 0:
            return

        use_restricted = True
        try:
            if self.db.get('apt-setup/restricted') == 'false':
                use_restricted = False
        except debconf.DebconfError:
            pass
        if not use_restricted:
            cache = self.restricted_cache
            for pkg in cache.keys():
                if (cache[pkg].is_installed and
                        cache[pkg].candidate.section.startswith(
                            'restricted/')):
                    difference.add(pkg)
            del cache

        install_misc.record_removed(difference)

        # Don't worry about failures removing packages; it will be easier
        # for the user to sort them out with a graphical package manager (or
        # whatever) after installation than it will be to try to deal with
        # them automatically here.
        (regular, recursive) = install_misc.query_recorded_removed()
        self.do_remove(regular)
        self.do_remove(recursive, recursive=True)

        oem_remove_extras = False
        try:
            oem_remove_extras = misc.create_bool(
                self.db.get('oem-config/remove_extras'))
        except debconf.DebconfError:
            pass

        if oem_remove_extras:
            installed = (desktop_packages | keep - regular - recursive)
            if not os.path.exists(self.target_file('var/lib/lingmo_installer')):
                os.makedirs(self.target_file('var/lib/lingmo_installer'))
            p = self.target_file('var/lib/lingmo_installer/installed-packages')
            with open(p, 'w') as fp:
                for line in installed:
                    print(line, file=fp)

    def copy_network_config(self):
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return
        try:
            if self.db.get('oem-config/enable') == 'true':
                return
        except debconf.DebconfError:
            pass

        source_nm = "/etc/NetworkManager/system-connections/"
        target_nm = "/target/etc/NetworkManager/system-connections/"

        # Sanity checks.  We don't want to do anything if a network
        # configuration already exists on the target
        if os.path.exists(source_nm) and os.path.exists(target_nm):
            for network in os.listdir(source_nm):
                # Skip LTSP live
                if network == "LTSP":
                    continue

                source_network = os.path.join(source_nm, network)
                target_network = os.path.join(target_nm, network)

                if os.path.exists(target_network):
                    continue

                shutil.copy(source_network, target_network)

        source_netplan = "/etc/netplan"
        target_netplan = "/target" + source_netplan
        if os.path.exists(source_netplan) and os.path.exists(target_netplan):
            for cfg in glob.glob("90-NM-*", root_dir=source_netplan):
                source_cfg = os.path.join(source_netplan, cfg)
                target_cfg = os.path.join(target_netplan, cfg)

                if os.path.exists(target_cfg):
                    continue

                shutil.copy(source_cfg, target_cfg)

    def copy_bluetooth_config(self):
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return
        try:
            if self.db.get('oem-config/enable') == 'true':
                return
        except debconf.DebconfError:
            pass

        source_bluetooth = "/var/lib/bluetooth/"
        target_bluetooth = "/target/var/lib/bluetooth/"

        # Ensure the target doesn't exist
        if os.path.exists(target_bluetooth):
            shutil.rmtree(target_bluetooth)

        # Copy /var/lib/bluetooth to /target/var/lib/bluetooth/
        if os.path.exists(source_bluetooth):
            shutil.copytree(source_bluetooth, target_bluetooth)

    def recache_apparmor(self):
        """Generate an apparmor cache to speed up boot time."""
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return
        if not os.path.exists(self.target_file('etc/init.d/apparmor')):
            syslog.syslog(
                'Apparmor is not installed, so not generating cache.')
            return
        install_misc.chrex(self.target, 'mount', '-t', 'proc', 'proc', '/proc')
        install_misc.chrex(
            self.target, 'mount', '-t', 'sysfs', 'sysfs', '/sys')
        install_misc.chrex(
            self.target, 'mount', '-t', 'securityfs',
            'securityfs', '/sys/kernel/security')
        install_misc.chrex(self.target, '/etc/init.d/apparmor', 'recache')
        install_misc.chrex(self.target, 'umount', '/proc')
        install_misc.chrex(self.target, 'umount', '/sys/kernel/security')
        install_misc.chrex(self.target, 'umount', '/sys')

    def copy_wallpaper_cache(self):
        """Copy GNOME wallpaper cache for the benefit of ureadahead.

        Only do this on systems with gnome-settings-daemon.
        """
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return

        # We don't use the copy_network_config live user trick as it's not
        # lingmo in install mode.
        try:
            live_user = pwd.getpwuid(999).pw_name
        except KeyError:
            # We're on a weird system where the live user isn't uid 999
            # just stop there
            return

        live_user_home = os.path.expanduser('~%s' % live_user)
        live_user_wallpaper_cache_dir = os.path.join(live_user_home, '.cache', 'wallpaper')
        target_user = self.db.get('passwd/username')
        target_user_cache_dir = self.target_file('home', target_user, '.cache')
        target_user_wallpaper_cache_dir = os.path.join(target_user_cache_dir,
                                                       'wallpaper')
        if (not os.path.isdir(target_user_wallpaper_cache_dir) and
                os.path.isdir(live_user_wallpaper_cache_dir)):

            # copy to targeted user
            uid = subprocess.Popen(
                ['chroot', self.target, 'sudo', '-u', target_user, '--',
                 'id', '-u'],
                stdout=subprocess.PIPE,
                universal_newlines=True).communicate()[0].strip('\n')
            gid = subprocess.Popen(
                ['chroot', self.target, 'sudo', '-u', target_user, '--',
                 'id', '-g'],
                stdout=subprocess.PIPE,
                universal_newlines=True).communicate()[0].strip('\n')
            uid = int(uid)
            gid = int(gid)
            self.copy_tree(live_user_wallpaper_cache_dir,
                           target_user_wallpaper_cache_dir, uid, gid)
            os.chmod(target_user_cache_dir, 0o700)
            os.chmod(target_user_wallpaper_cache_dir, 0o700)

    def copy_dcd(self):
        """Install the Distribution Channel Descriptor (DCD) file."""
        dcd = '/cdrom/.disk/lingmo_dist_channel'
        if os.path.exists(dcd):
            shutil.copy(dcd, self.target_file('var/lib/lingmo_dist_channel'))

    def copy_logs(self):
        """Copy log files to the installed system."""
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return

        target_dir = self.target_file('var/log/installer')
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        for log_file in ('/var/log/syslog', '/var/log/partman',
                         '/var/log/installer/version', '/var/log/live.log',
                         '/var/log/installer/debug', '/run/live-md5check.json'):
            target_log_file = os.path.join(target_dir,
                                           os.path.basename(log_file))
            if os.path.isfile(log_file):
                if not misc.execute('cp', '-a', log_file, target_log_file):
                    syslog.syslog(syslog.LOG_ERR,
                                  'Failed to copy installation log file')
                os.chmod(target_log_file, 0o640)
                os.chown(target_log_file, -1, grp.getgrnam('adm').gr_gid)
        media_info = '/cdrom/.disk/info'
        if os.path.isfile(media_info):
            try:
                target_media_info = \
                    self.target_file('var/log/installer/media-info')
                shutil.copy(media_info, target_media_info)
                os.chmod(target_media_info,
                         stat.S_IRUSR | stat.S_IWUSR |
                         stat.S_IRGRP | stat.S_IROTH)
            except (IOError, OSError):
                pass

        try:
            status = open(self.target_file('var/lib/dpkg/status'), 'rb')
            status_gz = gzip.open(os.path.join(target_dir,
                                               'initial-status.gz'), 'w')
            while True:
                data = status.read(65536)
                if not data:
                    break
                status_gz.write(data)
            status_gz.close()
            status.close()
        except IOError:
            pass
        try:
            if self.db.get('oem-config/enable') == 'true':
                oem_id = self.db.get('oem-config/id')
                tf = self.target_file('var/log/installer/oem-id')
                with open(tf, 'w') as oem_id_file:
                    print(oem_id, file=oem_id_file)
        except (debconf.DebconfError, IOError):
            pass

    def save_random_seed(self):
        """Save random seed to the target system.

        This arranges for the installed system to have better entropy on
        first boot.
        """
        if 'LINGMO-INSTALLER_OEM_USER_CONFIG' in os.environ:
            return

        try:
            st = os.stat("/dev/urandom")
        except OSError:
            return
        if not stat.S_ISCHR(st.st_mode):
            return
        if not os.path.isdir(self.target_file("var/lib/systemd")):
            return

        poolbytes = 512
        try:
            with open("/proc/sys/kernel/random/poolsize") as poolsize:
                poolbits = int(poolsize.readline())
                if poolbits:
                    poolbytes = int((poolbits + 7) / 8)
        except IOError:
            pass

        old_umask = os.umask(0o077)
        try:
            with open("/dev/urandom", "rb") as urandom:
                with open(self.target_file("var/lib/systemd/random-seed"),
                          "wb") as seed:
                    seed.write(urandom.read(poolbytes))
        except IOError:
            pass
        finally:
            os.umask(old_umask)

    def cleanup(self):
        """Miscellaneous cleanup tasks."""
        misc.execute('umount', self.target_file('cdrom'))

        env = dict(os.environ)
        env['OVERRIDE_BASE_INSTALLABLE'] = '1'
        subprocess.call(['/usr/lib/lingmo_installer/apt-setup/finish-install'],
                        env=env)

        for apt_conf in ('00NoMountCDROM', '00IgnoreTimeConflict',
                         '00AllowUnauthenticated'):
            osextras.unlink_force(
                self.target_file('etc/apt/apt.conf.d', apt_conf))


if __name__ == '__main__':
    os.environ['DPKG_UNTRANSLATED_MESSAGES'] = '1'
    if not os.path.exists('/var/lib/lingmo_installer'):
        os.makedirs('/var/lib/lingmo_installer')

    install = Install()
    sys.excepthook = install_misc.excepthook
    install.run()
    sys.exit(0)

# vim:ai:et:sts=4:tw=80:sw=4:
