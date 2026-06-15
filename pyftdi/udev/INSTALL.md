Udev rule for FTDI devices
=================================

1) Install rule (system-wide):

```
sudo cp pyftdi/udev/99-ftdi.rules /etc/udev/rules.d/99-ftdi.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

2) After installing, unplug & replug the FTDI device or reboot.

3) If you prefer to limit access to a group instead of world-writable, edit the rule to set `GROUP="plugdev"` and add your user to that group:

```
sudo usermod -a -G plugdev $USER
newgrp plugdev
```

4) Notes:
- The provided rule matches any USB device with vendor id `0403` (FTDI). If you prefer to match only specific FTDI product ids, uncomment or replace the example in `99-ftdi.rules`.
- Setting `MODE="0666"` gives everyone access; using `GROUP="plugdev"` is more secure.
