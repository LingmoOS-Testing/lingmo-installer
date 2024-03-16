#!/bin/sh

#
#  Put here every steps that must be executed on the target system and can not
#  be done with the iso-override facility
#

PREREQ=""
DESCRIPTION="Running custom script..."

prereqs()
{
       echo "$PREREQ"
}

case $1 in
# get pre-requisites
    prereqs)
       prereqs
       exit 0
       ;;
esac

. /scripts/live-functions

log_begin_msg "$DESCRIPTION"

sed -i 's/^%admin.*/%admin ALL=(ALL) NOPASSWD: ALL/' /root/etc/sudoers

# Workaround feature described in LP: #1283619
SHELL=/bin/sh chroot /root 2>/dev/null <<EOF
echo
echo "INFO: Applying workaround for 'tutorial' feature LP: #1283619"
mkdir -p /home/lingmo/.cache/unity/
touch /home/lingmo/.cache/unity/first_run.stamp
chown -R 999:999 /home/lingmo
EOF

log_end_msg
