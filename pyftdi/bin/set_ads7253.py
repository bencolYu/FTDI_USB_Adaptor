#!/usr/bin/env python3
"""Read ADS7253 ADC converter via SPI using PyFtdi.

ADS7253 Configuration:
- 16-CLK Single-SDO mode
- Pseudo-differential input with internal 2.5V reference
- Input range: 0-5V (2 × VREF)
- Simultaneous sampling of A and B channels
- Data output on SDO_A only

Usage examples:
  python3 pyftdi/bin/set_ads7253.py --read 10
  python3 pyftdi/bin/set_ads7253.py --url ftdi://ftdi:232h/1 --read 5
  python3 pyftdi/bin/set_ads7253.py --freq 16MHz --read 20 --quiet --batch-size 128
  python3 pyftdi/bin/set_ads7253.py --read 10000 --quiet --batch-size 128 --output ads7253_fast.csv
  python3 pyftdi/bin/set_ads7253.py --check
"""
import argparse
import csv
import sys
import time
from pathlib import Path
from struct import pack as spack

# Ensure the local pyftdi package in this repository is importable when running
# directly from the repository root or from the bin/ directory.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pyftdi.spi import SpiController
from pyftdi.ftdi import Ftdi
from ftdi_autodetect import (
    find_i2c_url,
    find_spi_url,
    make_ad5245_probe,
    make_si5351_probe,
)


# ADS7253 Configuration Constants
ADS7253_VREF = 2.5
ADS7253_FULL_SCALE = 2.0 * ADS7253_VREF  # 5.0V
ADS7253_MID_VOLTAGE = ADS7253_VREF  # 2.5V
ADS7253_MAX_CODE = 4095.0  # 12-bit
ADS7253_CFR_VALUE = 0x8EC0
ADS7253_FRAME_BYTES = 4
ADS7253_RECOMMENDED_BATCH_SIZE = 128


class ADS7253Controller:
    """Controller for ADS7253 ADC via SPI."""

    def __init__(self, spi_port, cs_pin=3):
        """Initialize ADS7253 controller.
        
        Args:
            spi_port: SPI port from SpiController
            cs_pin: Chip select pin (default ADBUS3)
        """
        self.port = spi_port
        self.cs_pin = cs_pin
        self.configured = False
        self.last_rx = bytes()
        self.last_raw = 0

    def write_cfr(self):
        """Write configuration register to ADS7253.
        
        In 16-CLK single-SDO mode, a frame uses 32 SCLKs (4 bytes).
        The first 16 bits contain the CFR command.
        """
        try:
            # CFR command (16 bits) + padding clocks.
            tx_data = [
                (ADS7253_CFR_VALUE >> 8) & 0xFF,
                ADS7253_CFR_VALUE & 0xFF,
            ]
            tx_data.extend([0x00] * (ADS7253_FRAME_BYTES - len(tx_data)))
            
            rx_data = self.port.exchange(tx_data, len(tx_data), duplex=True)
            self.last_rx = bytes(rx_data)
            print(f"✓ Wrote CFR = 0x{ADS7253_CFR_VALUE:04X}")
            print(f"  Response: {' '.join(f'{b:02X}' for b in rx_data)}")
            
            # Allow time for configuration to take effect
            time.sleep(0.001)
            
            # Perform dummy reads to allow configuration to settle
            for i in range(4):
                self.read_channels()
            
            self.configured = True
            return True
        except Exception as exc:
            print(f"✗ Failed to write CFR: {exc}", file=sys.stderr)
            return False

    def decode_raw(self, raw):
        """Decode one raw 16-CLK single-SDO frame.

        With this PyFtdi mode-1 setup, ADS7253 data is captured one bit later
        than the nominal mode-0 datasheet bit table. A midscale frame appears
        as 0x10001000, so the 12-bit channel fields are aligned at bits 28..17
        and 12..1 in the received 32-bit word.
        """
        return (raw >> 17) & 0x0FFF, (raw >> 1) & 0x0FFF

    def decode_variants(self):
        """Return useful alternate decodes for bring-up/debug."""
        raw = self.last_raw
        return {
            'default_a>>17_b>>1': ((raw >> 17) & 0x0FFF, (raw >> 1) & 0x0FFF),
            'datasheet_a>>18_b>>2': ((raw >> 18) & 0x0FFF, (raw >> 2) & 0x0FFF),
            'old_a>>18_b>>3': ((raw >> 18) & 0x0FFF, (raw >> 3) & 0x0FFF),
            'a>>19_b>>3': ((raw >> 19) & 0x0FFF, (raw >> 3) & 0x0FFF),
        }

    def read_channels(self):
        """Read both ADC channels (A and B) from ADS7253.
        
        In 16-CLK single-SDO mode with SPI mode 1 as used here, the received
        32-bit word is decoded as:
            bit31..bit29 bit28..bit17 bit16..bit13 bit12..bit1 bit0
                000        A[11:0]       0000       B[11:0]   0
        
        Returns:
            tuple: (code_a, code_b) or (None, None) on error
        """
        try:
            tx_data = [0x00] * ADS7253_FRAME_BYTES
            rx_data = self.port.exchange(tx_data, len(tx_data), duplex=True)
            self.last_rx = bytes(rx_data)
            
            raw = int.from_bytes(rx_data, byteorder='big')
            self.last_raw = raw
            
            # Extract 12-bit ADC values
            adc_a, adc_b = self.decode_raw(raw)
            
            return adc_a, adc_b
        except Exception as exc:
            print(f"✗ SPI read failed: {exc}", file=sys.stderr)
            return None, None

    def read_channels_batch(self, count):
        """Read multiple samples in one FTDI USB transaction.

        Each ADC sample still has its own CS-low/CS-high frame, but all MPSSE
        commands are queued and flushed together to reduce USB round trips.
        """
        if count <= 1:
            code_a, code_b = self.read_channels()
            if code_a is None:
                return []
            return [(code_a, code_b, self.last_rx, self.last_raw)]

        ctrl = self.port._controller
        if not ctrl.ftdi.is_connected:
            raise IOError('FTDI controller not initialized')

        frequency = self.port.frequency
        if self.port._cpha:
            frequency = (3 * frequency) // 2
        if ctrl._frequency != frequency:
            ctrl.ftdi.set_frequency(frequency)
            ctrl._frequency = frequency
        if ctrl._clock_phase != self.port._cpha:
            ctrl.ftdi.enable_3phase_clock(self.port._cpha)
            ctrl._clock_phase = self.port._cpha

        direction = ctrl.direction & 0xFF
        spi_mask = ctrl._spi_mask
        gpio_low = ctrl._gpio_low
        cpol = self.port._cpol
        rw_cmd = Ftdi.RW_BYTES_PVE_NVE_MSB if not cpol else Ftdi.RW_BYTES_NVE_PVE_MSB
        frame = [0x00] * ADS7253_FRAME_BYTES

        cmd = bytearray()
        for _ in range(count):
            for level in self.port._cs_prolog:
                cmd.extend((Ftdi.SET_BITS_LOW, (level & spi_mask) | gpio_low, direction))
            cmd.extend(spack('<BH', rw_cmd, len(frame) - 1))
            cmd.extend(frame)
            for level in self.port._cs_epilog:
                cmd.extend((Ftdi.SET_BITS_LOW, (level & spi_mask) | gpio_low, direction))
            cmd.extend((Ftdi.SET_BITS_LOW, ctrl._cs_bits | gpio_low, direction))

        cmd.append(Ftdi.SEND_IMMEDIATE)
        ctrl.ftdi.write_data(cmd)
        read_attempts = max(8, min(64, (count + 31) // 32))
        expected_len = ADS7253_FRAME_BYTES * count
        data = ctrl.ftdi.read_data_bytes(expected_len, read_attempts)
        if len(data) != expected_len:
            raise IOError(f'Expected {expected_len} bytes from FTDI, got {len(data)}')

        samples = []
        for index in range(count):
            start = index * ADS7253_FRAME_BYTES
            rx_data = bytes(data[start:start + ADS7253_FRAME_BYTES])
            raw = int.from_bytes(rx_data, byteorder='big')
            code_a, code_b = self.decode_raw(raw)
            samples.append((code_a, code_b, rx_data, raw))

        if samples:
            self.last_rx = samples[-1][2]
            self.last_raw = samples[-1][3]
        return samples

    def code_to_voltage(self, code):
        """Convert ADC code to voltage.
        
        Args:
            code: 12-bit ADC code (0-4095)
            
        Returns:
            float: Voltage in volts (0-5V)
        """
        return (code * ADS7253_FULL_SCALE) / ADS7253_MAX_CODE

    def code_to_ac(self, code):
        """Convert ADC code to AC signal (around 2.5V midpoint).
        
        Args:
            code: 12-bit ADC code
            
        Returns:
            float: AC voltage deviation from midpoint (-2.5V to +2.5V)
        """
        return self.code_to_voltage(code) - ADS7253_MID_VOLTAGE


def parse_frequency(value: str) -> int:
    """Parse frequency argument supporting various formats.
    
    Args:
        value: Frequency string (e.g., '16000000', '16M', '16MHz')
        
    Returns:
        int: Frequency in Hz
    """
    try:
        value_upper = value.upper()
        
        if value_upper.endswith('MHZ'):
            return int(value_upper.replace('MHZ', '')) * 1000000
        elif value_upper.endswith('KHZ'):
            return int(value_upper.replace('KHZ', '')) * 1000
        elif value_upper.endswith('HZ'):
            return int(value_upper.replace('HZ', ''))
        elif value_upper.endswith('M'):
            return int(value_upper[:-1]) * 1000000
        elif value_upper.endswith('K'):
            return int(value_upper[:-1]) * 1000
        else:
            return int(value)
    except Exception:
        raise argparse.ArgumentTypeError(f"invalid frequency value: '{value}'")


def main(argv=None):
    p = argparse.ArgumentParser(
        description='Read ADS7253 ADC converter via SPI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test communication (read once)
  python3 pyftdi/bin/set_ads7253.py --check
  
  # Read 10 samples
  python3 pyftdi/bin/set_ads7253.py --read 10
  
  # Use specific FTDI device and SPI frequency
  python3 pyftdi/bin/set_ads7253.py --url ftdi://ftdi:232h/1 --freq 16MHz --read 50
  
  # Fast CSV capture without printing every sample
  python3 pyftdi/bin/set_ads7253.py --read 1000 --quiet --batch-size 128 --output ads7253.csv
  python3 pyftdi/bin/set_ads7253.py --read 10000 --quiet --batch-size 128 --output ads7253_fast.csv
  
  # Continuous reading (Ctrl+C to stop)
  python3 pyftdi/bin/set_ads7253.py --read 0
        """
    )
    p.add_argument(
        '--url', default='auto',
        help='FTDI URL, or auto to use the non-I2C FTDI cable (default: auto)'
    )
    p.add_argument(
        '--i2c-url', default='auto',
        help='I2C FTDI URL used only to exclude that cable during SPI auto-detect'
    )
    p.add_argument(
        '--freq', type=parse_frequency, default=16000000,
        help='SPI frequency (default: 16MHz). Supports Hz/KHz/MHz (e.g., 16MHz, 16000000)'
    )
    p.add_argument(
        '--check', action='store_true',
        help='Check communication: configure ADS7253 and read once'
    )
    p.add_argument(
        '--read', type=int, nargs='?', const=0,
        help='Read N samples. Use 0 for continuous reading (Ctrl+C to stop)'
    )
    p.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show raw data and response bytes'
    )
    p.add_argument(
        '--output', '-o',
        help='Save readings to a CSV file that can be opened in Excel'
    )
    p.add_argument(
        '--mode', type=int, choices=[0, 1, 2, 3], default=1,
        help='SPI mode (default: 1 for ADS7253 with this FTDI setup)'
    )
    p.add_argument(
        '--decode-diagnostics', action='store_true',
        help='Show alternate raw-frame decodes for bit-alignment debugging'
    )
    p.add_argument(
        '--interval', type=float, default=0.0,
        help='Delay between read batches in seconds (default: 0 for fastest capture)'
    )
    p.add_argument(
        '--quiet', action='store_true',
        help='Do not print every sample; useful for faster CSV capture'
    )
    p.add_argument(
        '--batch-size', type=int, default=ADS7253_RECOMMENDED_BATCH_SIZE,
        help=f'Samples per FTDI USB transaction for faster capture (default: {ADS7253_RECOMMENDED_BATCH_SIZE})'
    )
    
    args = p.parse_args(argv)

    # Validate frequency
    if args.freq < 1000 or args.freq > 30000000:
        p.error('SPI frequency must be between 1 kHz and 30 MHz for FT232H/PyFtdi')
    if args.interval < 0:
        p.error('--interval must be zero or positive')
    if args.batch_size < 1:
        p.error('--batch-size must be at least 1')
    if args.batch_size > ADS7253_RECOMMENDED_BATCH_SIZE:
        print(
            f'Warning: batch sizes above {ADS7253_RECOMMENDED_BATCH_SIZE} may time out '
            'on this FTDI/USB setup',
            file=sys.stderr)

    # At least one action required
    if not args.check and args.read is None:
        p.error('specify --check or --read')

    spi_ctrl = None
    try:
        if args.url == 'auto' or args.url == 'ftdi:///1':
            i2c_detected = find_i2c_url((
                make_si5351_probe(0xC0),
                make_ad5245_probe(0x2C),
            ), args.i2c_url)
            print(f"Auto-detected I2C FTDI device: {i2c_detected.url} ({i2c_detected.detail})")
            spi_detected = find_spi_url(
                args.url, exclude_urls=(i2c_detected.url,), frequency=args.freq)
            print(f"Auto-selected SPI FTDI device: {spi_detected.url} ({spi_detected.detail})")
            args.url = spi_detected.url

        # Initialize SPI controller
        spi_ctrl = SpiController()
        print(f"Configuring FTDI device: {args.url}")
        print(f"SPI frequency: {args.freq / 1e6:.1f} MHz")
        print(f"SPI mode: {args.mode}")
        print("ADS7253 interface: 16-CLK Single-SDO")
        spi_ctrl.configure(args.url, frequency=args.freq)
        
        # Get SPI port with CS slot 0 (ADBUS3 on FTDI devices)
        spi_port = spi_ctrl.get_port(0, freq=args.freq, mode=args.mode)
        
        # Initialize ADS7253 controller
        ads = ADS7253Controller(spi_port)
        
        print("Initializing ADS7253...")
        if not ads.write_cfr():
            return 2
        
        print("ADS7253 Configuration:\n")
        print("  Mode:           Pseudo-Differential, 16-CLK Single-SDO")
        print(f"  CFR:            0x{ADS7253_CFR_VALUE:04X}")
        print(f"  Frame clocks:   {ADS7253_FRAME_BYTES * 8}")
        print("  Input range:    0 - 5V")
        print("  Reference:      Internal 2.5V")
        print("  Channels:       A (voltage sensing), B (current sensing)")
        print("  Midpoint:       2.5V (AC signal around this point)\n")
        
        # Handle --check: single read to verify communication
        if args.check:
            print("Reading channels...")
            code_a, code_b = ads.read_channels()
            if code_a is not None:
                volt_a = ads.code_to_voltage(code_a)
                ac_a = ads.code_to_ac(code_a)
                volt_b = ads.code_to_voltage(code_b)
                ac_b = ads.code_to_ac(code_b)
                
                print(f"\n✓ Communication successful!\n")
                print("Channel A (Voltage Sensing):")
                print(f"  Code:       {code_a:4d}")
                print(f"  Voltage:    {volt_a:.5f} V")
                print(f"  AC signal:  {ac_a:.5f} V")
                print(f"\nChannel B (Current Sensing):")
                print(f"  Code:       {code_b:4d}")
                print(f"  Voltage:    {volt_b:.5f} V")
                print(f"  AC signal:  {ac_b:.5f} V")
                
                if args.verbose:
                    print(f"\nRaw bytes: {' '.join(f'{b:02X}' for b in ads.last_rx)}")
                if args.decode_diagnostics:
                    print("\nDecode diagnostics:")
                    for name, (diag_a, diag_b) in ads.decode_variants().items():
                        print(f"  {name}: A={diag_a:4d}, B={diag_b:4d}")
            else:
                print("✗ Failed to read from ADS7253")
                return 3

        # Handle --read: continuous or N samples
        elif args.read is not None:
            sample_count = 0
            csv_file = None
            csv_writer = None
            try:
                if args.output:
                    csv_file = open(args.output, 'w', newline='', encoding='utf-8')
                    csv_writer = csv.writer(csv_file)
                    csv_writer.writerow([
                        'sample',
                        'timestamp_s',
                        'code_a',
                        'voltage_a_v',
                        'ac_a_v',
                        'code_b',
                        'voltage_b_v',
                        'ac_b_v',
                        'raw_hex',
                    ])
                    print(f"Saving readings to: {args.output}")

                print("Reading channels...\n")
                print("Format: Code_A, Voltage_A, AC_A | Code_B, Voltage_B, AC_B\n")
                start_time = time.time()
                
                while True:
                    if args.read > 0:
                        remaining = args.read - sample_count
                        if remaining <= 0:
                            break
                        batch_count = min(args.batch_size, remaining)
                    else:
                        batch_count = args.batch_size

                    try:
                        samples = ads.read_channels_batch(batch_count)
                    except Exception as exc:
                        print(f"✗ SPI batch read failed: {exc}", file=sys.stderr)
                        return 3

                    for code_a, code_b, rx_data, raw in samples:
                        ads.last_rx = rx_data
                        ads.last_raw = raw
                        sample_time = time.time() - start_time
                        volt_a = ads.code_to_voltage(code_a)
                        ac_a = ads.code_to_ac(code_a)
                        volt_b = ads.code_to_voltage(code_b)
                        ac_b = ads.code_to_ac(code_b)
                        raw_hex = ' '.join(f'{b:02X}' for b in rx_data)
                        
                        if not args.quiet:
                            print(f"A: {code_a:4d}, {volt_a:.5f}V, AC {ac_a:+.5f}V | "
                                  f"B: {code_b:4d}, {volt_b:.5f}V, AC {ac_b:+.5f}V")
                        if args.verbose:
                            print(f"  Raw: {raw_hex}")
                        if args.decode_diagnostics:
                            variants = ', '.join(
                                f'{name}:A={diag_a}/B={diag_b}'
                                for name, (diag_a, diag_b) in ads.decode_variants().items())
                            print(f"  Decodes: {variants}")

                        if csv_writer:
                            csv_writer.writerow([
                                sample_count + 1,
                                f'{sample_time:.6f}',
                                code_a,
                                f'{volt_a:.6f}',
                                f'{ac_a:.6f}',
                                code_b,
                                f'{volt_b:.6f}',
                                f'{ac_b:.6f}',
                                raw_hex,
                            ])
                        
                        sample_count += 1
                        if args.read > 0 and sample_count >= args.read:
                            break
                    
                    if args.interval:
                        time.sleep(args.interval)
                    
            except KeyboardInterrupt:
                print(f"\n\nStopped after {sample_count} samples")
            finally:
                if csv_file:
                    csv_file.close()
                if sample_count:
                    elapsed = time.time() - start_time
                    rate = sample_count / elapsed if elapsed else 0.0
                    print(f"Captured {sample_count} samples in {elapsed:.3f}s ({rate:.1f} samples/s)")

    except Exception as exc:
        print(f'\n✗ Failed to initialize FTDI/ADS7253: {exc}', file=sys.stderr)
        return 1
    finally:
        if spi_ctrl is not None:
            try:
                spi_ctrl.close()
            except Exception:
                pass

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
