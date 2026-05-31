# Si5351A Clock Control - Complete Solution

## Overview

A comprehensive single-command solution for controlling the Silicon Labs Si5351A frequency generator with individual clock output enable/disable capability.

---

## Quick Start (30 seconds)

```bash
# 1. Navigate to workspace
cd /home/bencolyu/FTDI_USB_Adaptor

# 2. Set frequency with controls
./si.sh freq 113000

# 3. Control individual outputs
./si.sh clk0 enable
./si.sh clk1 disable

# 4. Check status
./si.sh status
```

---

## What's New

### Single Command Control
✅ **Set frequency** with `./si.sh freq <Hz>`  
✅ **Enable/disable/toggle** individual clock outputs  
✅ **Check status** anytime with `./si.sh status`  
✅ **Preview changes** with `--dry-run`

### Key Features
- Individual control of CLK0, CLK1, CLK2
- Combine frequency setting and output control in one command
- Simple wrapper script (`si.sh`) for easy access
- Full Python API for advanced scripts
- Comprehensive documentation

---

## Files in This Solution

### Core Files (What You'll Use)

| File | Purpose |
|------|---------|
| `si.sh` | **Main wrapper** - Use this for most commands |
| `pyftdi/bin/set_si5351.py` | Enhanced Python script with clock control |

### Documentation

| File | Purpose |
|------|---------|
| `SINGLE_COMMAND_CONTROL.md` | **Start here** - Complete guide with all commands |
| `CLOCK_CONTROL_REFERENCE.md` | Advanced reference with detailed examples |
| `EXAMPLES.sh` | Practical usage examples and scenarios |
| `README_CLOCK_CONTROL.md` | This file |

---

## Command Reference

### The Easiest Way (Using `si.sh`)

```bash
# Frequency control
./si.sh freq 113000              # Set CLK0 to 113 kHz
./si.sh freq 50000 clk0+clk1     # Configure both CLK0 and CLK1

# Output control
./si.sh clk0 enable              # Enable CLK0
./si.sh clk1 disable             # Disable CLK1
./si.sh clk2 toggle              #Toggle CLK2

# Status
./si.sh status                   # Show current output states
./si.sh crystal                  # Check crystal health
```

### Python Script (For Advanced Control)

```bash
# Set frequency and control multiple outputs
python3 pyftdi/bin/set_si5351.py --freq 113000 \
  --clk0 enable --clk1-ctrl disable --clk2-ctrl enable

# Control without frequency change
python3 pyftdi/bin/set_si5351.py --clk0 enable --clk1-ctrl disable

# Check status
python3 pyftdi/bin/set_si5351.py --show-output
```

---

## Implementation Details

### What Was Enhanced

**In `set_si5351.py`:**
- Added `--clk0`, `--clk1-ctrl`, `--clk2-ctrl` arguments
- New `format_output_state()` function
- New `control_clock_output()` function
- Improved `--show-output` display
- Better dry-run handling

**New `si.sh` wrapper:**
- Simple command syntax
- Automatic argument translation
- Help display
- Error checking

### Register Control

The solution controls Si5351A register 0x03 (OUTPUT_ENABLE_CTRL):
- Bit 0 = CLK0 (0=enabled, 1=disabled)
- Bit 1 = CLK1 (0=enabled, 1=disabled)
- Bit 2 = CLK2 (0=enabled, 1=disabled)

---

## Usage Scenarios

### Scenario 1: Simple Frequency Output
```bash
./si.sh freq 113000
```
Sets CLK0 to 113 kHz, CLK0 enabled, others disabled.

### Scenario 2: Multiple Clock Outputs
```bash
./si.sh freq 100000 clk0+clk1
./si.sh status
```
Configures CLK0 and CLK1 to 100 kHz, displays status.

### Scenario 3: Dynamic Output Control
```bash
# Initial setup
./si.sh freq 113000

# Later, enable CLK1
./si.sh clk1 enable

# Verify
./si.sh status
```

### Scenario 4: Testing Changes Safely
```bash
# Preview without applying
./si.sh freq 113000 --dry-run

# Apply when confident
./si.sh freq 113000
```

---

## Supported Options

### Clock Control Arguments
- `clk0 {enable|disable|toggle}` - Control CLK0
- `clk1 {enable|disable|toggle}` - Control CLK1 (note: use `clk1-ctrl` in Python script)
- `clk2 {enable|disable|toggle}` - Control CLK2

### Configuration Arguments
- `--freq <Hz>` - Output frequency in Hz
- `--addr <0xXX>` - I2C address (default: 0xC0)
- `--url <ftdi://...>` - FTDI device URL (default: ftdi:///1)
- `--load {6,8,10}` - Load capacitance in pF
- `--dry-run` - Preview without applying changes

### Query Arguments
- `--show-output` - Display current output state
- `--check-crystal` - Check crystal lock status

---

## Verification

After setting frequency, verify configuration:

```bash
# Check outputs are as expected
./si.sh status

# Check crystal is locked
./si.sh crystal

# Full debug output
./si.sh freq 113000 2>&1 | grep DEBUG
```

---

## Troubleshooting

### Device not responding?
```bash
./si.sh crystal  # Check if crystal is detected
```

### Want to see what changed?
```bash
./si.sh freq 113000 --dry-run  # Preview mode
```

### Multiple devices on same bus?
```bash
./si.sh freq 113000 --addr 0xC0  # Device 1
./si.sh freq 50000 --addr 0xC2   # Device 2
```

---

## Advanced Examples

See `EXAMPLES.sh` for practical code examples covering:
- Basic frequency setting
- Output control
- Status verification
- Multi-device control
- Dry-run testing
- Complete workflows

---

## Next Steps

1. **Try a simple command:** `./si.sh freq 113000`
2. **Check status:** `./si.sh status`
3. **Read full docs:** See `SINGLE_COMMAND_CONTROL.md`
4. **Explore examples:** See `EXAMPLES.sh`

---

## For More Information

- **Complete guide:** [SINGLE_COMMAND_CONTROL.md](SINGLE_COMMAND_CONTROL.md)
- **Reference:** [CLOCK_CONTROL_REFERENCE.md](CLOCK_CONTROL_REFERENCE.md)
- **Examples:** [EXAMPLES.sh](EXAMPLES.sh)

---

## Version History

**Current Version: 1.0**
- ✅ Individual clock output control (enable/disable/toggle)
- ✅ Status reporting with readable output format
- ✅ Convenience wrapper script for easy access
- ✅ Dry-run mode for safe testing
- ✅ Multi-device support
- ✅ Comprehensive documentation

---

## Support

For the most common tasks:
```bash
./si.sh                    # Help
./si.sh freq 113000        # Set frequency
./si.sh clk0 enable        # Control output
./si.sh status             # Check status
```

That's it! You now have complete clock control in a single command.
