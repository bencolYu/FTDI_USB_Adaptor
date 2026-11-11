#!/usr/bin/env python3
"""Configure SI5351A output using PyFtdi I2C.

Examples:
  # Set frequency on CLK0
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 100000
  
  # Set frequency and control specific outputs
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk0 enable --clk1-ctrl disable
  
  # Enable/disable individual clock outputs without changing frequency
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 enable
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 disable
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk1-ctrl toggle
  
  # Show current output state
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output
  
  # Configure both CLK0 and CLK1
  python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 100000 --clk1
  
  # Set frequency and 50% duty cycle on CLK0 for 10 milliseconds
  python3 pyftdi/bin/set_si5351.py 100000 10ms 50%

  # Duty-cycle mode stays active until Ctrl+C is pressed
  python3 pyftdi/bin/set_si5351.py 100000 100ms 1%  # Ctrl+C to exit the command
"""

import argparse
import math
import os
import sys
import re
import time
from fractions import Fraction

# When this script is executed from the repository root using
# python3 pyftdi/bin/set_si5351.py, the package root is not on sys.path.
# Add the repository root so local pyftdi can be imported.
here = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(here)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from pyftdi.i2c import I2cController
from ftdi_autodetect import find_i2c_url, make_ad5245_probe, make_si5351_probe


SI5351_CLK0_CTRL = 0x10
SI5351_CLK1_CTRL = 0x11
SI5351_OUTPUT_ENABLE_CTRL = 0x03
SI5351_PLL_A = 0x1A
SI5351_MS0 = 0x2A
SI5351_MS1 = 0x34
SI5351_PLL_RESET = 0xB1
SI5351_LOAD_CAP_CTRL = 0xB7

XTAL_FREQ = 25_000_000
CLK0_FREQ_MIN_HZ = 70_000
CLK0_FREQ_MAX_HZ = 150_000

R_DIV_VALUES = [1, 2, 4, 8, 16, 32, 64, 128]
# SI5351A output load capacitance control for register 183 (0xB7)
# 0x00 -> 0 pF, 0x40 -> 6 pF, 0x80 -> 8 pF, 0xC0 -> 10 pF
LOAD_CAP_VALUES = {6: 0x40, 8: 0x80, 10: 0xC0}


def parse_int(value: str) -> int:
    try:
        if value.startswith(('0b', '0B')):
            return int(value, 2)
        if value.startswith(('0x', '0X')):
            return int(value, 16)
        return int(value, 0)
    except Exception:
        raise argparse.ArgumentTypeError(f"invalid integer value: '{value}'")


def pll_params(a: int, b: int, c: int):
    p1 = 128 * a + (128 * b) // c - 512
    p2 = (128 * b) % c
    p3 = c
    return p1, p2, p3


def multisynth_params(ms: float):
    integer = int(math.floor(ms))
    frac = Fraction(ms - integer).limit_denominator(1 << 20)
    if frac.numerator == 0:
        return integer, 0, 1
    return integer, frac.numerator, frac.denominator


def reg_bytes(p1: int, p2: int, p3: int, r_div: int = 0, div_by_4: int = 0):
    if not 0 <= r_div <= 7:
        raise ValueError('R divider code must be 0..7')
    if not 0 <= div_by_4 <= 3:
        raise ValueError('DIVBY4 code must be 0..3')
    return [
        (p3 >> 8) & 0xFF,
        p3 & 0xFF,
        ((r_div & 0x07) << 4) | ((div_by_4 & 0x03) << 2) | ((p1 >> 16) & 0x03),
        (p1 >> 8) & 0xFF,
        p1 & 0xFF,
        (p2 >> 16) & 0x0F,
        (p2 >> 8) & 0xFF,
        p2 & 0xFF,
    ]


def choose_r_div_and_ms(freq_hz: float, pll_freq_hz: float = 900e6) -> tuple[int, float, int]:
    if freq_hz <= 0:
        raise ValueError('Frequency must be positive')
    if freq_hz > 200e6:
        raise ValueError('Frequency out of range; Si5351A max output is 200 MHz')

    # For outputs above 150 MHz, a divide-by-4 output mode is required.
    if freq_hz > 150e6:
        fvco = freq_hz * 4
        if fvco < 600e6 or fvco > 900e6:
            raise ValueError('Frequency out of range for high-frequency divide-by-4 mode')
        return 1, 4.0, 3

    best = None
    for r_div in R_DIV_VALUES:
        ms = pll_freq_hz / (freq_hz * r_div)
        if 8 <= ms <= 2048:
            ms_int, ms_num, ms_den = multisynth_params(ms)
            actual_ms = ms_int + (ms_num / ms_den if ms_den else 0)
            actual_fout = pll_freq_hz / (actual_ms * r_div)
            error = abs(actual_fout - freq_hz)
            if best is None or error < best[0] or (
                    abs(error - best[0]) <= 1e-12 and r_div > best[1]):
                best = (error, r_div, ms)
    if best is None:
        raise ValueError('Frequency out of range for the selected PLL frequency')
    return best[1], best[2], 0


def write_register(port, reg_addr: int, value: int) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError('Register value out of byte range')
    print(f'DEBUG: Write reg 0x{reg_addr:02X} <- 0x{value:02X}', file=sys.stderr)
    port.write([reg_addr, value])


def write_block(port, reg_addr: int, values: list[int]) -> None:
    print(f'DEBUG: Write block at 0x{reg_addr:02X}: {" ".join(f"0x{v:02X}" for v in values)}', file=sys.stderr)
    for offset, value in enumerate(values):
        write_register(port, reg_addr + offset, value)


def read_register(port, reg_addr: int) -> int:
    """Read a single byte from a device register and return it as int.

    Uses the I2cPort.read_from helper which sends the register address
    then reads back the requested number of bytes.
    """
    data = port.read_from(reg_addr, readlen=1)
    if not data:
        raise IOError(f'No data read from register {reg_addr}')
    return data[0]


def parse_registers_header(path: str) -> list:
    """Parse a ClockBuilder C header export containing
    an array of register entries like: { 0x0002, 0x53 },
    Returns list of (addr, value) tuples.
    """
    regs = []
    pat = re.compile(r"\{\s*0x([0-9A-Fa-f]+)\s*,\s*0x([0-9A-Fa-f]+)\s*\}")
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            m = pat.search(line)
            if m:
                addr = int(m.group(1), 16)
                val = int(m.group(2), 16)
                regs.append((addr, val))
    return regs


def apply_register_list(port, regs: list, dry_run: bool = False) -> None:
    """Write a list of (addr, val) to the device. If dry_run, only print."""
    for addr, val in regs:
        reg = addr & 0xFF
        if dry_run:
            print('DRY RUN: write 0x%02X <- 0x%02X' % (reg, val))
        else:
            write_register(port, reg, val)


def to_7bit_address(addr: int) -> int:
    if addr > 0x7F:
        if addr & 1:
            raise ValueError('Provided I2C address appears to be odd 8-bit value')
        return addr >> 1
    return addr


def format_output_state(reg3: int) -> str:
    """Format OUTPUT_ENABLE_CTRL register state to readable string."""
    enabled = []
    for i in range(3):
        if not (reg3 & (1 << i)):
            enabled.append(f'CLK{i}')
    if not enabled:
        return 'All outputs DISABLED'
    return ', '.join(enabled) + ' enabled'


def control_clock_output(port, clk_num: int, action: str, current_state: int) -> int:
    """Control individual clock output enable/disable.
    
    Args:
        port: I2C port
        clk_num: Clock number (0, 1, or 2)
        action: 'enable', 'disable', or 'toggle'
        current_state: Current value of OUTPUT_ENABLE_CTRL register (0x03)
    
    Returns:
        Updated register value
    """
    if not 0 <= clk_num <= 2:
        raise ValueError('Clock number must be 0, 1, or 2')
    
    # Bit positions: CLK0=bit0, CLK1=bit1, CLK2=bit2 (0=enabled, 1=disabled)
    bit_mask = 1 << clk_num
    
    if action == 'enable':
        new_state = current_state & ~bit_mask  # Clear bit to enable
    elif action == 'disable':
        new_state = current_state | bit_mask   # Set bit to disable
    elif action == 'toggle':
        new_state = current_state ^ bit_mask   # Toggle bit
    else:
        raise ValueError(f"Invalid action: {action}")
    
    if current_state != new_state:
        print(f'CLK{clk_num} {action}: {format_output_state(current_state)} -> {format_output_state(new_state)}', file=sys.stderr)
        write_register(port, SI5351_OUTPUT_ENABLE_CTRL, new_state)
    else:
        print(f'CLK{clk_num} already {action}d: {format_output_state(current_state)}', file=sys.stderr)
    
    return new_state


def parse_period_ms(value: str) -> int:
    """Parse a duration like '10ms' or '100' and return milliseconds."""
    text = str(value).strip().lower()
    if not text:
        raise argparse.ArgumentTypeError('period is empty')
    if text.endswith('ms'):
        text = text[:-2]
    elif text.endswith('msec'):
        text = text[:-4]
    try:
        period_ms = int(float(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid period value: '{value}'") from exc
    if period_ms <= 0:
        raise argparse.ArgumentTypeError('period must be > 0 ms')
    return period_ms


def parse_duty_percent(value: str) -> int:
    """Parse a duty cycle like '50%' or '50' and return a 0..100 value."""
    text = str(value).strip().lower()
    if not text:
        raise argparse.ArgumentTypeError('duty cycle is empty')
    if text.endswith('%'):
        text = text[:-1]
    try:
        duty = int(float(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid duty cycle: '{value}'") from exc
    if not 0 <= duty <= 100:
        raise argparse.ArgumentTypeError('duty cycle must be in the range 0..100%')
    return duty


def set_clk0_output_state(port, enabled: bool, current_state: int | None = None) -> int:
    """Set CLK0 enabled/disabled while preserving other output bits."""
    if current_state is None:
        current_state = read_register(port, SI5351_OUTPUT_ENABLE_CTRL)

    bit_mask = 1 << 0
    if enabled:
        new_state = current_state & ~bit_mask
    else:
        new_state = current_state | bit_mask

    if current_state != new_state:
        print(f'CLK0 {"enabled" if enabled else "disabled"}: 0x{current_state:02X} -> 0x{new_state:02X}', file=sys.stderr)
        write_register(port, SI5351_OUTPUT_ENABLE_CTRL, new_state)
    else:
        print(f'CLK0 already {"enabled" if enabled else "disabled"}', file=sys.stderr)
    return new_state


def apply_duty_cycle(port, duty_percent: int, period_ms: int = 1000, steps: int = 100,
                    initial_state: int | None = None, repeat: bool = False) -> int:
    """Approximate the requested duty cycle on CLK0 by toggling the output.

    When repeat=True, the pattern is generated continuously until interrupted.
    """
    if not 0 <= duty_percent <= 100:
        raise ValueError('Duty cycle must be between 0 and 100 inclusive')
    if period_ms <= 0:
        raise ValueError('Period must be positive')
    if steps <= 0:
        raise ValueError('Steps must be positive')

    current_state = read_register(port, SI5351_OUTPUT_ENABLE_CTRL) if initial_state is None else initial_state

    if duty_percent == 0:
        return set_clk0_output_state(port, enabled=False, current_state=current_state)
    if duty_percent == 100:
        return set_clk0_output_state(port, enabled=True, current_state=current_state)

    on_steps = int(round((duty_percent / 100.0) * steps))
    if on_steps == 0:
        on_steps = 1
    if on_steps == steps:
        on_steps = steps - 1

    step_time = period_ms / steps
    print(f'Applying {duty_percent}% duty cycle on CLK0 for {period_ms} ms ({on_steps}/{steps} enabled steps)', file=sys.stderr)

    if repeat:
        print('Duty-cycle output will repeat until Ctrl-C. CLK0 remains active while the pattern is running.', file=sys.stderr)

    while True:
        # Start each cycle with CLK0 enabled so the output is active during the on-phase.
        current_state = set_clk0_output_state(port, enabled=True, current_state=current_state)
        for index in range(steps):
            enabled = index < on_steps
            current_state = set_clk0_output_state(port, enabled=enabled, current_state=current_state)
            if index < steps - 1:
                time.sleep(step_time / 1000.0)

        if not repeat:
            current_state = set_clk0_output_state(port, enabled=True, current_state=current_state)
            return current_state

        # Keep repeating the cycle continuously; this is the pattern visible on an oscilloscope.
        # Note: The actual timing accuracy may vary depending on the system and load conditions.
        # For precise timing requirements, an external timing source or trigger may be needed.
        # This loop is intended for basic duty cycle approximation and testing.
        # If higher precision is required, consider using a dedicated timer or PWM controller.
        # The Si5351A can also be configured to generate precise frequencies and duty cycles
        # without the need for software timing loops.
        # Refer to the Si5351A datasheet and programming guide for more information.
        # For continuous operation, ensure that the I2C bus remains active and the device
        # is not put into a low-power or sleep mode that could disrupt the output.
        # Some experimentation may be needed to achieve the desired results in a specific
        # application or test setup.
        # If the output needs to be stopped, the function can be interrupted with Ctrl-C,
        # which will raise a KeyboardInterrupt exception. The caller can handle this exception
        # to perform any necessary cleanup or reconfiguration.
        # Example:
        # try:
        #     apply_duty_cycle(port, 50, 1000, repeat=True)
        # except KeyboardInterrupt:
        #     print("Duty cycle output stopped by user")
        #     # Perform any cleanup or reconfiguration here
        #     set_clk0_output_state(port, enabled=False)
        #     write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0xFF)  # Disable all outputs
        #     # Optionally, reconfigure the device or enter a low-power mode
        #     # write_register(port, SI5351_PLL_RESET, 0x00)  # Example: Reset PLL
        #     # time.sleep(0.1)  # Wait for PLL to stabilize
        #     # write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0x00)  # Disable outputs
        #     # Optionally, re-enter the previous configuration or a safe state
        #     # write_register(port, SI5351_PLL_A, previous_p1, previous_p2, previous_p3)
        #     # write_register(port, SI5351_MS0, previous_ms0_values)
        #     # write_register(port, SI5351_MS1, previous_ms1_values)
        #     # write_register(port, SI5351_CLK0_CTRL, previous_clk0_ctrl)
        #     # write_register(port, SI5351_CLK1_CTRL, previous_clk1_ctrl)
        #     # write_register(port, SI5351_LOAD_CAP_CTRL, previous_load_cap)
        #     # write_register(port, SI5351_PLL_RESET, previous_pll_reset)
        #     # write_register(port, SI5351_OUTPUT_ENABLE_CTRL, previous_output_enable)
        #     # time.sleep(0.1)  # Wait for reconfiguration to take effect
        #     # print("Device reconfigured to previous state")
        #     # or enter a low-power mode
        #     # write_register(port, SI5351_PLL_RESET, 0x00)  # Example: Reset PLL
        #     # time.sleep(0.1)  # Wait for PLL to stabilize
        #     # write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0x00)  # Disable outputs
        #     # print("Device entered low-power mode")
        #     pass
        # finally:
        #     set_clk0_output_state(port, enabled=True)  # Ensure CLK0 remains enabled
        #     print("Cleanup complete, CLK0 enabled")
        #     return current_state


def main(argv=None):
    p = argparse.ArgumentParser(description='Configure SI5351A CLK0 output over I2C')
    p.add_argument('--url', default='auto',
                   help='FTDI URL for PyFtdi, or auto to probe connected FTDI cables')
    p.add_argument('--addr', default='0xC0', type=parse_int,
                   help='8-bit I2C write address (default: 0xC0)')
    p.add_argument('--freq', default=100000, type=parse_int,
                   help='CLK0 output frequency in Hz, allowed range 70000-150000 (default: 100000)')
    p.add_argument('--load', default=8, type=parse_int,
                   choices=sorted(LOAD_CAP_VALUES.keys()),
                   help='CLK0 load capacitance in pF (6, 8, 10; default: 8)')
    p.add_argument('--check-crystal', action='store_true',
                   help='Read register 0 and report LOS_XTAL (bit 3)')
    p.add_argument('--check-output', action='store_true',
                   help='Read register 3 and report output enable state')
    p.add_argument('--show-output', action='store_true',
                   help='Show current output enable state (shorthand for --check-output)')
    p.add_argument('--clk1', action='store_true',
                   help='Also configure CLK1 with same settings as CLK0')
    p.add_argument('--clk0', choices=['enable', 'disable', 'toggle'],
                   help='Control CLK0 output (enable/disable/toggle)')
    p.add_argument('--clk1-ctrl', choices=['enable', 'disable', 'toggle'],
                   help='Control CLK1 output (enable/disable/toggle)')
    p.add_argument('--clk2-ctrl', choices=['enable', 'disable', 'toggle'],
                   help='Control CLK2 output (enable/disable/toggle)')
    p.add_argument('--apply-registers', default=None,
                   help='Path to ClockBuilder C header to apply register writes')
    p.add_argument('--dry-run', action='store_true',
                   help='Print register writes instead of performing them')
    p.add_argument('--period-ms', default=None, type=parse_period_ms,
                   help='Duty-cycle period in milliseconds, e.g. 10ms or 100')
    p.add_argument('--duty-cycle', default=None, type=parse_duty_percent,
                   help='Duty-cycle percentage, e.g. 50% or 50')
    p.add_argument('freq_positional', nargs='?', type=parse_int,
                   help='Optional positional frequency in Hz for duty-cycle mode')
    p.add_argument('period_positional', nargs='?',
                   help='Optional positional period in ms, e.g. 10ms')
    p.add_argument('duty_positional', nargs='?',
                   help='Optional positional duty cycle, e.g. 50%')
    args = p.parse_args(argv)

    if args.freq_positional is not None:
        args.freq = args.freq_positional
    if args.period_positional is not None:
        args.period_ms = parse_period_ms(args.period_positional)
    if args.duty_positional is not None:
        args.duty_cycle = parse_duty_percent(args.duty_positional)

    if getattr(args, 'duty_cycle', None) is not None:
        if getattr(args, 'period_ms', None) is None:
            args.period_ms = 1000
        duty_percent = args.duty_cycle
        period_ms = args.period_ms
        freq_hz = float(args.freq)
        if freq_hz <= 0:
            p.error('Frequency must be positive')
        if not CLK0_FREQ_MIN_HZ <= freq_hz <= CLK0_FREQ_MAX_HZ:
            p.error(f'CLK0 frequency out of range: {args.freq} Hz. Allowed range is {CLK0_FREQ_MIN_HZ} Hz to {CLK0_FREQ_MAX_HZ} Hz.')
    else:
        duty_percent = None
        period_ms = None

    addr = to_7bit_address(args.addr)
    freq_hz = float(args.freq)
    load_pf = args.load
    if freq_hz <= 0:
        p.error('Frequency must be positive')
    if not CLK0_FREQ_MIN_HZ <= freq_hz <= CLK0_FREQ_MAX_HZ:
        p.error(
            f'CLK0 frequency out of range: {args.freq} Hz. '
            f'Allowed range is {CLK0_FREQ_MIN_HZ} Hz to {CLK0_FREQ_MAX_HZ} Hz.')
    
    # Handle --show-output shorthand
    if args.show_output:
        args.check_output = True

    # Use PLLA fixed at 900 MHz for the main frequency range.
    r_div, ms, div_by_4 = choose_r_div_and_ms(freq_hz)
    pll_a_a = 36
    pll_a_b = 0
    pll_a_c = 1
    p1_pll, p2_pll, p3_pll = pll_params(pll_a_a, pll_a_b, pll_a_c)
    ms_int, ms_num, ms_den = multisynth_params(ms)
    p1_ms, p2_ms, p3_ms = pll_params(ms_int, ms_num, ms_den)
    
    # Debug output
    print(f'DEBUG: Target frequency: {freq_hz} Hz', file=sys.stderr)
    print(f'DEBUG: Chosen R_DIV: {r_div}, MS: {ms:.10f}, DIVBY4={div_by_4}', file=sys.stderr)
    print(f'DEBUG: MS_int={ms_int}, MS_num={ms_num}, MS_den={ms_den}', file=sys.stderr)
    print(f'DEBUG: PLL params - P1={p1_pll}, P2={p2_pll}, P3={p3_pll}', file=sys.stderr)
    print(f'DEBUG: MS params - P1={p1_ms}, P2={p2_ms}, P3={p3_ms}', file=sys.stderr)

    try:
        detected = find_i2c_url((
            make_si5351_probe(addr),
            make_ad5245_probe(0x2C),
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
        port = ctrl.get_port(addr)
        print('Using I2C address 0x%02X (7-bit)' % addr)

        # If requested, apply a ClockBuilder export header directly.
        if args.apply_registers:
            regs = parse_registers_header(args.apply_registers)
            if not regs:
                print('No register entries found in %s' % args.apply_registers, file=sys.stderr)
                return 5
            print('Applying %d register writes from %s' % (len(regs), args.apply_registers))
            apply_register_list(port, regs, dry_run=args.dry_run)
            if args.dry_run:
                print('Dry run complete; no registers written')
                return 0
            print('Register block applied')
            return 0

        # If requested, read register 0 and report LOS_XTAL (bit 3)
        if args.check_crystal:
            try:
                reg0 = read_register(port, 0)
            except Exception as exc:
                print(f'Failed to read register 0: {exc}', file=sys.stderr)
                return 4
            los = bool(reg0 & 0x08)
            lol_b = bool(reg0 & 0x20)
            lol_a = bool(reg0 & 0x40)
            print(f'Register 0 = 0x{reg0:02X}')
            if los:
                print('LOS_XTAL=1 -> crystal NOT detected', file=sys.stderr)
                return 5
            else:
                print('LOS_XTAL=0 -> crystal OK')
                if lol_a:
                    print('LOL_A=1 -> PLLA loss-of-lock', file=sys.stderr)
                    return 6
                else:
                    print('LOL_A=0 -> PLLA locked')
                if lol_b:
                    print('LOL_B=1 -> PLLB loss-of-lock', file=sys.stderr)
                else:
                    print('LOL_B=0 -> PLLB locked')
                return 0

        # If requested, read register 3 and report output enable state
        if args.check_output:
            try:
                reg3 = read_register(port, 3)
            except Exception as exc:
                print(f'Failed to read register 3: {exc}', file=sys.stderr)
                return 4
            print(f'Register 3 (OUTPUT_ENABLE_CTRL) = 0x{reg3:02X}')
            print(f'Output state: {format_output_state(reg3)}')
            return 0

        load_value = LOAD_CAP_VALUES[load_pf]
        outputs_str = 'CLK0+CLK1' if args.clk1 else 'CLK0'
        print('Configuring SI5351A for %s Hz on %s using PLLA=900MHz, R_div=%s MS=%s, DIVBY4=%s, load=%spF' %
              (freq_hz, outputs_str, r_div, ms, div_by_4, load_pf))

        # Set the requested crystal load capacitance first.
        write_register(port, SI5351_LOAD_CAP_CTRL, load_value)

        # Disable all outputs while programming.
        write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0xFF)

        # Program PLL A.
        write_block(port, SI5351_PLL_A, reg_bytes(p1_pll, p2_pll, p3_pll))

        # Program MS0 for CLK0 output.
        write_block(port, SI5351_MS0, reg_bytes(p1_ms, p2_ms, p3_ms, R_DIV_VALUES.index(r_div), div_by_4))

        # Program MS1 for CLK1 output if requested.
        if args.clk1:
            write_block(port, SI5351_MS1, reg_bytes(p1_ms, p2_ms, p3_ms, R_DIV_VALUES.index(r_div), div_by_4))

        # Configure CLK0 output driver as PLLA/MS0 source and enable it.
        write_register(port, SI5351_CLK0_CTRL, 0x0F)

        # Configure CLK1 output driver as PLLA/MS1 source if requested.
        if args.clk1:
            write_register(port, SI5351_CLK1_CTRL, 0x0F)

        # Reset PLLA/PLLB so the new configuration takes effect.
        write_register(port, SI5351_PLL_RESET, 0xAC)

        # Determine output enable bits: CLK0=bit0, CLK1=bit1, CLK2=bit2
        # 0xFE = CLK0 only enabled (0b11111110)
        # 0xFC = CLK0+CLK1 enabled  (0b11111100)
        # 0xFB = CLK0+CLK2 enabled  (0b11111011)
        # 0xFA = CLK0+CLK1+CLK2 enabled (0b11111010)
        # 0xFF = All outputs disabled
        output_enable_val = 0xFC if args.clk1 else 0xFE
        write_register(port, SI5351_OUTPUT_ENABLE_CTRL, output_enable_val)
        
        # Apply individual clock control commands if provided
        # These override the default behavior set above
        if args.clk0 or args.clk1_ctrl or args.clk2_ctrl:
            if not args.dry_run:
                reg3 = read_register(port, SI5351_OUTPUT_ENABLE_CTRL)
                print(f'Current OUTPUT_ENABLE_CTRL = 0x{reg3:02X}', file=sys.stderr)
                if args.clk0:
                    reg3 = control_clock_output(port, 0, args.clk0, reg3)
                if args.clk1_ctrl:
                    reg3 = control_clock_output(port, 1, args.clk1_ctrl, reg3)
                if args.clk2_ctrl:
                    reg3 = control_clock_output(port, 2, args.clk2_ctrl, reg3)
            else:
                print('DRY RUN: Clock control would be applied', file=sys.stderr)
                reg3 = 0xFE

        if duty_percent is not None:
            print(f'Applying duty-cycle mode: {duty_percent}% at {period_ms} ms on CLK0 at {freq_hz} Hz', file=sys.stderr)
            reg3 = read_register(port, SI5351_OUTPUT_ENABLE_CTRL)
            try:
                reg3 = apply_duty_cycle(port, duty_percent, period_ms=period_ms, steps=100, initial_state=reg3, repeat=True)
            except KeyboardInterrupt:
                print('Duty-cycle run interrupted; restoring CLK0 enabled', file=sys.stderr)
                reg3 = set_clk0_output_state(port, enabled=True, current_state=reg3)
            print(f'Duty cycle set to {duty_percent}% over {period_ms} ms', file=sys.stderr)

        outputs_done = 'CLK0+CLK1' if args.clk1 else 'CLK0'
        print('SI5351A configured for %.0f Hz on %s' % (freq_hz, outputs_done))
    except Exception as exc:
        print(f'I2C operation failed: {exc}', file=sys.stderr)
        return 3
    finally:
        ctrl.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
