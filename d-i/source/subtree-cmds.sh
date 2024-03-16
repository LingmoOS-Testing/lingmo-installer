#!/bin/sh
set -x
set -e
#git subtree add --prefix=d-i/source/apt-setup https://git.launchpad.net/~lingmo-installer/apt-setup '1%0.157lingmo2'
#git subtree add --prefix=d-i/source/base-installer https://git.launchpad.net/~lingmo-installer/base-installer 1.158lingmo7
#git subtree add --prefix=d-i/source/bterm-unifont https://git.launchpad.net/bterm-unifont 1.6
#git subtree add --prefix=d-i/source/choose-mirror https://git.launchpad.net/~lingmo-installer/choose-mirror 2.78lingmo7
#git subtree add --prefix=d-i/source/clock-setup https://git.launchpad.net/~lingmo-installer/clock-setup 0.131lingmo1
git subtree add --prefix=d-i/source/console-setup https://git.launchpad.net/lingmo/+source/console-setup lingmo/devel
git subtree add --prefix=d-i/source/debian-installer-utils https://git.launchpad.net/~lingmo-installer/debian-installer-utils 1.124lingmo1
git subtree add --prefix=d-i/source/grub-installer https://git.launchpad.net/~lingmo-installer/grub-installer 1.128lingmo14
git subtree add --prefix=d-i/source/hw-detect https://git.launchpad.net/~lingmo-installer/hw-detect 1.117lingmo7
git subtree add --prefix=d-i/source/localechooser https://git.launchpad.net/lingmo/+source/localechooser lingmo/devel
git subtree add --prefix=d-i/source/netcfg https://git.launchpad.net/~lingmo-installer/netcfg 1.142lingmo8
git subtree add --prefix=d-i/source/partconf https://git.launchpad.net/~lingmo-installer/partconf 1.50lingmo1
git subtree add --prefix=d-i/source/partman-auto https://git.launchpad.net/~lingmo-installer/partman-auto 134lingmo13
git subtree add --prefix=d-i/source/partman-auto-crypto https://git.launchpad.net/~lingmo-installer/partman-auto-crypto 25lingmo1
git subtree add --prefix=d-i/source/partman-auto-loop https://git.launchpad.net/~lingmo-installer/partman-auto-loop 0lingmo21
git subtree add --prefix=d-i/source/partman-auto-lvm https://git.launchpad.net/~lingmo-installer/partman-auto-lvm 59lingmo4
git subtree add --prefix=d-i/source/partman-base https://git.launchpad.net/~lingmo-installer/partman-base 206lingmo6
git subtree add --prefix=d-i/source/partman-basicfilesystems https://git.launchpad.net/~lingmo-installer/partman-basicfilesystems 127lingmo2
git subtree add --prefix=d-i/source/partman-basicmethods https://git.launchpad.net/~lingmo-installer/partman-basicmethods 70
git subtree add --prefix=d-i/source/partman-btrfs https://git.launchpad.net/~lingmo-installer/partman-btrfs 29lingmo1
git subtree add --prefix=d-i/source/partman-crypto https://git.launchpad.net/~lingmo-installer/partman-crypto 101lingmo4
git subtree add --prefix=d-i/source/partman-efi https://git.launchpad.net/~lingmo-installer/partman-efi 84lingmo1
git subtree add --prefix=d-i/source/partman-ext3 https://git.launchpad.net/~lingmo-installer/partman-ext3  86lingmo1
git subtree add --prefix=d-i/source/partman-jfs https://git.launchpad.net/~lingmo-installer/partman-jfs 58
git subtree add --prefix=d-i/source/partman-lvm https://git.launchpad.net/partman-lvm 133
git subtree add --prefix=d-i/source/partman-partitioning https://git.launchpad.net/~lingmo-installer/partman-partitioning 120lingmo3
git subtree add --prefix=d-i/source/partman-swapfile https://git.launchpad.net/partman-swapfile 2
git subtree add --prefix=d-i/source/partman-target https://git.launchpad.net/~lingmo-installer/partman-target 98lingmo1
git subtree add --prefix=d-i/source/partman-xfs https://git.launchpad.net/~lingmo-installer/partman-xfs 66
git subtree add --prefix=d-i/source/preseed https://git.launchpad.net/~lingmo-installer/preseed 1.71lingmo11
git subtree add --prefix=d-i/source/tzsetup https://git.launchpad.net/~lingmo-installer/tzsetup '1%0.94lingmo2'
git subtree add --prefix=d-i/source/user-setup https://git.launchpad.net/lingmo/+source/user-setup lingmo/devel
