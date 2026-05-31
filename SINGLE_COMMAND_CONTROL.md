# Si5351A Single Command Control Solution

## Summary

You now have a complete command-line solution to control the Si5351A frequency generator with individual clock output enable/disable control. The solution includes:

1. **Enhanced Python Script** - `pyftdi/bin/set_si5351.py`
2. **Convenience Wrapper** - `si.sh`
3. **Comprehensive Documentation** - `CLOCK_CONTROL_REFERENCE.md`

---

## Quick Start

### Single Command to Control Everything

```bash
# Set frequency and control outputs in one command
./si.sh freq 113000 clk0+clk1

# Enable/disable individual clocks without changing frequency
./si.sh clk0 enable
./si.sh clk1 disable
./si.sh clk2 toggle

# Check current state
./si.sh status
```

---

## Core Commands

### Using the Wrapper (Recommended - Simpler)

```bash
# Set frequency
./si.sh freq 113000

# Set frequency with multiple clocks
./si.sh freq 113000 clk0+clk1

# Control individual outputs
./si.sh clk0 enable
./si.sh clk0 disable
./si.sh clk0 toggle
./si.sh clk1 disable
./si.sh clk2 enable

# Show current status
./si.sh status
./si.sh show

# Check crystal
./si.sh crystal
```

### Using Python Script Directly

```bash
# Set frequency with CLK0 only
python3 pyftdi/bin/set_si5351.py --freq 113000

# Set frequency with multiple clocks  
python3 pyftdi/bin/set_si5351.py --freq 113000 --clk1

# Full control with individual outputs
python3 pyftdi/bin/set_si5351.py --freq 113000 --clk0 enable --clk1-ctrl disable --clk2-ctrl enable

# Control without changing frequency
python3 pyftdi/bin/set_si5351.py --clk0 enable --clk1-ctrl disable

# Check status
python3 pyftdi/bin/set_si5351.py --show-output
```

---

## Features Added

### 1. Individual Clock Output Control

| Command | Effect |
|---------|--------|
| `--clk0 enable` | Enable CLK0 output |
| `--clk0 disable` | Disable CLK0 output |
| `--clk0 toggle` | Toggle CLK0 state |
| `--clk1-ctrl enable` | Enable CLK1 output |
| `--clk1-ctrl disable` | Disable CLK1 output |
| `--clk1-ctrl toggle` | Toggle CLK1 state |
| `--clk2-ctrl enable` | Enable CLK2 output |
| `--clk2-ctrl disable` | Disable CLK2 output |
| `--clk2-ctrl toggle` | Toggle CLK2 state |

### 2. Status Commands

```bash
# Show which outputs are currently enabled
python3 pyftdi/bin/set_si5351.py --show-output

# Alternative
python3 pyftdi/bin/set_si5351.py --check-output

# Output example:
# Register 3 (OUTPUT_ENABLE_CTRL) = 0xFE
# Output state: CLK0 enabled
```

### 3. Wrapper Functions

**format_output_state(register)** - Converts register value to readable format:
- `0xFE` → "CLK0 enabled"
- `0xFC` → "CLK0, CLK1 enabled"
- `0xFF` → "All outputs DISABLED"

**control_clock_output(port, clock_num, action, state)** - Manages individual output control

---

## Advanced Examples

### Complete Configuration in Single Command

```bash
# Set frequency to 113kHz, enable CLK0, disable CLK1, enable CLK2
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 \
  --clk0 enable --clk1-ctrl disable --clk2-ctrl enable
```

### Multi-Step Configuration

```bash
# Step 1: Set frequency with default outputs
./si.sh freq 100000

# Step 2: Check current state
./si.sh status

# Step 3: Modify outputs as needed
./si.sh clk1 enable
./si.sh clk2 disable

# Step 4: Verify final state
./si.sh status
```

### Working with Multiple Devices

```bash
# Use different I2C addresses
./si.sh freq 113000 --addr 0xC0
./si.sh freq 100000 --addr 0xC2

# Use different FTDI devices
./si.sh freq 113000 --url ftdi://128/1
./si.sh freq 100000 --url ftdi://128/2
```

---

## Implementation Details

### Python Script Changes

**New Helper Functions:**
- `format_output_state(reg3)` - Formats register output to readable text
- `control_clock_output(port, clk_num, action, current_state)` - Controls individual clock enable/disable/toggle

**New Arguments:**
- `--clk0` - Control CLK0 (enable/disable/toggle)
- `--clk1-ctrl` - Control CLK1 (enable/disable/toggle)
- `--clk2-ctrl` - Control CLK2 (enable/disable/toggle)
- `--show-output` - Display current output state

**Improved Dry-Run Mode:**
- Clock control operations skip device reads in dry-run mode
- Simulates state transitions for preview

### Shell Wrapper Features

- Simplified command syntax
- Passes arguments through to Python script
- Supports `--addr` and `--url` options
- Handles `--dry-run` flag
- Provides help with no arguments

---

## Register Encoding Reference

Silicon Labs Si5351A OUTPUT_ENABLE_CTRL Register (0x03):

| Value | Bit Pattern | Description |
|-------|-------------|-------------|
| 0xFE | 11111110 | CLK0 only (CLK1, CLK2 disabled) |
| 0xFD | 11111101 | CLK1 only (CLK0, CLK2 disabled) |
| 0xFB | 11111011 | CLK2 only (CLK0, CLK1 disabled) |
| 0xFC | 11111100 | CLK0 + CLK1 (CLK2 disabled) |
| 0xFA | 11111010 | CLK0 + CLK2 (CLK1 disabled) |
| 0xF9 | 11111001 | CLK1 + CLK2 (CLK0 disabled) |
| 0xF8 | 11111000 | CLK0 + CLK1 + CLK2 (all enabled) |
| 0xFF | 11111111 | All disabled |

Bit mapping: 0=enabled, 1=disabled
- Bit 0 = CLK0
- Bit 1 = CLK1
- Bit 2 = CLK2

---

## Testing

### Dry-Run Mode (Safe Testing)

```bash
# Preview what would happen without making actual changes
./si.sh freq 113000 --dry-run

python3 pyftdi/bin/set_si5351.py --freq 113000 --clk0 enable --dry-run
```

### Verify with Status Checks

```bash
# After configuration, verify the settings took effect
./si.sh status
./si.sh crystal
```

---

## Files Modified/Created

1. **Enhanced**: `pyftdi/bin/set_si5351.py` - Added clock control features
2. **Created**: `si.sh` - Convenience wrapper script
3. **Created**: `CLOCK_CONTROL_REFERENCE.md` - Complete reference guide
4. **Created**: `SINGLE_COMMAND_CONTROL.md` - This file

---

## Default Settings

- Default I2C Address: `0xC0` (7-bit: 0x60)
- Default FTDI URL: `ftdi:///1`
- Default Frequency: `100000` Hz (100 kHz)
- Default Load Capacitance: `8` pF
- Default Crystal Frequency: 25 MHz

Override any default:

```bash
./si.sh freq 113000 --addr 0xC2
./si.sh status --url ftdi://128/2
```

---

## Troubleshooting

### Device Not Found
```bash
# Check if FTDI device is connected and permissions are correct
python3 pyftdi/bin/set_si5351.py --check-crystal
```

### Crystal Not Detected
```bash
# Check crystal status
./si.sh crystal
```

### Get Debug Output
```bash
# All writes are shown in stderr (starting with "DEBUG:")
./si.sh freq 113000 2>&1 | grep DEBUG
```

---

## Summary

You now have a complete, single-command system to:
✅ Set frequency on any clock output
✅ Enable/disable/toggle individual clocks independently
✅ Query current output state
✅ Test with dry-run mode
✅ Work with multiple devices via different addresses/URLs
✅ Debug with verbose output

All in a single command line!
