#!/usr/bin/env bash
# This script "unlocks" an OpenStack VM, allowing you to login without being able to contact the
# Kerberos or RADIUS server for authentication.
# Currently, this script only supports unlocking VMs configured to authenticate with Kerberos, but
# support for RADIUS VMs may be added in the future.
set -e
# Connect and mount the image.
modprobe nbd max_part=16
qemu-nbd --connect=/dev/nbd0 "$1"
mkdir -p /mnt/cloudimg
set +e
waitcount=0
while ! mount /dev/nbd0p1 /mnt/cloudimg; do
    if [ $waitcount -ge 6 ]; then
	echo "Coult not find device /dedv/nbd0p1!"
	exit 1
    fi
    waitcount=$((waitcount+1))
    sleep 5
done
set -e
cd /mnt/cloudimg/etc/pam.d
# Don't use Kerberos with PAM.
find . -type f -exec sed -i "/pam_krb5/d" {} \;
sed -i 's/\(password.*\)use_authtok \(.*\)/\1\2/' common-password
cd /mnt/cloudimg
# Changge the password of ubuntu.
chroot . passwd ubuntu
# Unmount the image.
cd /
umount /mnt/cloudimg
# Perform e2fsck on image.
e2fsck -p /dev/nbd0p1
# Disconnect.
qemu-nbd --disconnect /dev/nbd0
