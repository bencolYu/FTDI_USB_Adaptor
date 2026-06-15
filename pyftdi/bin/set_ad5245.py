#!/usr/bin/env python3
"""Set AD5245 wiper via I2C using PyFtdi.

Usage examples:
  python3 pyftdi/bin/set_ad5245.py 128
  python3 pyftdi/bin/set_ad5245.py --addr 0b0101100 200
  python3 pyftdi/bin/set_ad5245.py --url ftdi://ftdi:232h/1 --addr 0x2C --reg 0 42
"""
import argparse
import sys
from pathlib import Path

# Ensure the local pyftdi package in this repository is importable when running
# directly from the repository root or from the bin/ directory.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pyftdi.i2c import I2cController
from ftdi_autodetect import find_i2c_url, make_ad5245_probe, make_si5351_probe


def parse_int(value: str) -> int:
    try:
        if value.startswith(('0b', '0B')):
            return int(value, 2)
        if value.startswith(('0x', '0X')):
            return int(value, 16)
        return int(value, 0)
    except Exception:
        raise argparse.ArgumentTypeError(f"invalid integer value: '{value}'")


def main(argv=None):
    p = argparse.ArgumentParser(description='Write and/or read AD5245 via I2C')
    p.add_argument('--url', default='auto',
                   help='FTDI URL, or auto to probe connected FTDI cables (default: auto)')
    p.add_argument('--addr', default='0b0101100', type=parse_int,
                   help='7-bit I2C address (bin/hex/dec). Default: 0b0101100')
    p.add_argument('--cmd', type=parse_int, default=0x00,
                   help='AD5245 command/instruction byte. Default: 0x00 for RDAC')
    p.add_argument('--read', action='store_true',
                   help='Read back the selected register after writing')
    p.add_argument('value', nargs='?', type=parse_int,
                   help='Value to write (0-255). Omit when only reading.')
    args = p.parse_args(argv)

    if args.value is not None and not 0 <= args.value <= 0xFF:
        p.error('value must be between 0 and 255')
    if args.value is None and not args.read:
        p.error('either a value to write or --read must be provided')

    try:
        detected = find_i2c_url((
            make_ad5245_probe(int(args.addr), int(args.cmd)),
            make_si5351_probe(0xC0),
        ), args.url)
        if args.url == 'auto' or detected.url != args.url:
            print(f'Auto-selected I2C FTDI device: {detected.url} ({detected.detail})')
        args.url = detected.url
    except Exception as exc:
        print(f'Failed to auto-detect I2C FTDI device: {exc}', file=sys.stderr)
        return 2

    ctrl = I2cController()
    try:
        ctrl.configure(args.url)
    except Exception as exc:
        print(f'Failed to open FTDI device: {exc}', file=sys.stderr)
        return 2

    try:
        port = ctrl.get_port(int(args.addr))
        if args.value is not None:
            port.write([args.cmd, args.value])
            print(f'Wrote {args.value} to AD5245 at 0x{int(args.addr):02X}, cmd 0x{args.cmd:02X}')
        if args.read:
            data = port.exchange([args.cmd], 1)
            print(f'Readback: {int(data[0])} (0x{int(data[0]):02X})')
    except Exception as exc:
        print(f'I2C operation failed: {exc}', file=sys.stderr)
        return 3
    finally:
        ctrl.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
