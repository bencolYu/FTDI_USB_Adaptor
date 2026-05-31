# Si5351A Clock Control Reference

## Overview
The enhanced `set_si5351.py` script now supports individual clock output control using command-line arguments.

## Basic Usage

### Set frequency with default clock outputs
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000
```
Sets CLK0 to 113 kHz and enables it.

### Configure multiple clocks
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk1
```
Configures both CLK0 and CLK1 with the same frequency.

## Clock Output Control

### Enable/Disable individual clock outputs

**Enable CLK0:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 enable
```

**Disable CLK0:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 disable
```

**Toggle CLK0 (enable→disable or disable→enable):**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 toggle
```

### Control multiple outputs simultaneously

**Set frequency AND control outputs:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk0 enable --clk1-ctrl disable --clk2-ctrl enable
```

**Control CLK1 and CLK2 without changing frequency:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk1-ctrl enable --clk2-ctrl disable
```

**Toggle CLK1:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk1-ctrl toggle
```

**Toggle CLK2:**
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk2-ctrl toggle
```

## Status Checking

### Check output enable state
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output
```

Or equivalently:
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-output
```

Sample output:
```
Register 3 (OUTPUT_ENABLE_CTRL) = 0xFE
Output state: CLK0 enabled
```

### Check crystal status
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal
```

## Advanced Combinations

### Set frequency on CLK0, enable CLK1, disable CLK2
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 100000 --clk0 enable --clk1-ctrl enable --clk2-ctrl disable
```

### Configure CLK0 with 50% duty cycle settings and keep CLK1 disabled
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 200000 --load 10 --clk0 enable --clk1-ctrl disable
```

### Dry-run to see what would happen without making changes
```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk0 enable --dry-run
```

## Clock Arguments Summary

| Argument | Values | Description |
|----------|--------|-------------|
| `--clk0` | `enable`/`disable`/`toggle` | Control CLK0 output |
| `--clk1-ctrl` | `enable`/`disable`/`toggle` | Control CLK1 output |
| `--clk2-ctrl` | `enable`/`disable`/`toggle` | Control CLK2 output |
| `--show-output` | - | Display current output state |

## Output Register Encoding

The Si5351A uses register 0x03 (OUTPUT_ENABLE_CTRL) to control outputs:
- Bits 0-2 control CLK0, CLK1, CLK2 respectively
- 0 = output enabled
- 1 = output disabled

Common register values:
- `0xFE` = CLK0 enabled only (0b11111110)
- `0xFD` = CLK1 enabled only (0b11111101)
- `0xFB` = CLK2 enabled only (0b11111011)
- `0xFC` = CLK0 + CLK1 enabled (0b11111100)
- `0xFA` = CLK0 + CLK2 enabled (0b11111010)
- `0xFF` = All outputs disabled

## Examples with FTDI Device Discovery

If you have multiple FTDI devices, specify the device:

```bash
# List connected FTDI devices
python3 -c "from pyftdi.usbtools import UsbTools; UsbTools.list_devices()"

# Use specific device URL (e.g., first device on bus 1)
python3 pyftdi/bin/set_si5351.py --url ftdi://128/1 --addr 0xC0 --freq 113000
```

## Verification Commands

After configuration, verify the settings took effect:

```bash
# Check crystal is working
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal

# Check which outputs are enabled
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output
```
