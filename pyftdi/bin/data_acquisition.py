#!/usr/bin/env python3
"""Timed single-sample ADS7253 data acquisition.

This script reads one ADS7253 A/B sample per requested interval. It does not
use the bulk-read path.

Usage examples:
  python3 pyftdi/bin/data_acquisition.py --sample-interval 100ms --sample-period 10s
  python3 pyftdi/bin/data_acquisition.py --sample-interval 300ms --sample-period 10s --output ads7253_single.csv
"""
import argparse
import csv
import sys
import time
from pathlib import Path

# Ensure the local pyftdi package in this repository is importable when running
# directly from the repository root or from the bin/ directory.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pyftdi.spi import SpiController
from ftdi_autodetect import (
    find_i2c_url,
    find_spi_url,
    make_ad5245_probe,
    make_si5351_probe,
)
from set_ads7253 import ADS7253Controller, parse_frequency


INVALID_RAW_FRAMES = (0x00000000, 0xFFFFFFFF)
DEFAULT_ADC_RETRIES = 3
DEFAULT_RETRY_DELAY = 0.1


def parse_duration(value: str) -> float:
    """Parse a duration argument supporting seconds and milliseconds."""
    try:
        text = value.strip().lower()
        if text.endswith('milliseconds'):
            seconds = float(text[:-12]) / 1000.0
        elif text.endswith('millisecond'):
            seconds = float(text[:-11]) / 1000.0
        elif text.endswith('msec'):
            seconds = float(text[:-4]) / 1000.0
        elif text.endswith('ms'):
            seconds = float(text[:-2]) / 1000.0
        elif text.endswith('seconds'):
            seconds = float(text[:-7])
        elif text.endswith('second'):
            seconds = float(text[:-6])
        elif text.endswith('sec'):
            seconds = float(text[:-3])
        elif text.endswith('s'):
            seconds = float(text[:-1])
        else:
            seconds = float(text)
    except Exception:
        raise argparse.ArgumentTypeError(f"invalid duration value: '{value}'")

    if seconds <= 0:
        raise argparse.ArgumentTypeError(f"duration must be positive: '{value}'")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Timed single-sample ADS7253 acquisition',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 pyftdi/bin/data_acquisition.py --sample-interval 100ms --sample-period 10s
  python3 pyftdi/bin/data_acquisition.py --sample-interval 300ms --sample-period 10s --output ads7253_single.csv
        """
    )
    parser.add_argument(
        '--url', default='auto',
        help='FTDI URL, or auto to use the non-I2C FTDI cable (default: auto)'
    )
    parser.add_argument(
        '--i2c-url', default='auto',
        help='I2C FTDI URL used only to exclude that cable during SPI auto-detect'
    )
    parser.add_argument(
        '--freq', type=parse_frequency, default=16000000,
        help='SPI frequency (default: 16MHz). Supports Hz/KHz/MHz (e.g., 16MHz, 16000000)'
    )
    parser.add_argument(
        '--mode', type=int, choices=[0, 1, 2, 3], default=1,
        help='SPI mode (default: 1 for ADS7253 with this FTDI setup)'
    )
    parser.add_argument(
        '--sample-interval', required=True, type=parse_duration,
        help='Time between single ADC samples, e.g. 100ms, 300ms, or 0.1s'
    )
    parser.add_argument(
        '--sample-period', required=True, type=parse_duration,
        help='Total acquisition period, e.g. 10s or 10'
    )
    parser.add_argument(
        '--output', '-o', default='data_acquisition.csv',
        help='CSV output file (default: data_acquisition.csv)'
    )
    parser.add_argument(
        '--quiet', action='store_true',
        help='Do not print every sample'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show raw response bytes'
    )
    parser.add_argument(
        '--adc-retries', type=int, default=DEFAULT_ADC_RETRIES,
        help=f'Retry failed or invalid ADC samples this many times (default: {DEFAULT_ADC_RETRIES})'
    )
    parser.add_argument(
        '--retry-delay', type=float, default=DEFAULT_RETRY_DELAY,
        help=f'Delay before retrying a failed ADC sample, seconds (default: {DEFAULT_RETRY_DELAY})'
    )

    args = parser.parse_args(argv)

    if args.freq < 1000 or args.freq > 30000000:
        parser.error('SPI frequency must be between 1 kHz and 30 MHz for FT232H/PyFtdi')
    if args.adc_retries < 0:
        parser.error('--adc-retries must be zero or positive')
    if args.retry_delay < 0:
        parser.error('--retry-delay must be zero or positive')

    spi_ctrl = None
    ads = None
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

        def close_ads_connection():
            nonlocal spi_ctrl, ads
            if spi_ctrl is not None:
                try:
                    spi_ctrl.close()
                except Exception:
                    pass
                spi_ctrl = None
            ads = None

        def open_ads_connection(announce=False):
            nonlocal spi_ctrl, ads
            close_ads_connection()
            spi_ctrl = SpiController()
            if announce:
                print(f"Configuring FTDI device: {args.url}")
                print(f"SPI frequency: {args.freq / 1e6:.1f} MHz")
                print(f"SPI mode: {args.mode}")
                print("ADS7253 interface: 16-CLK Single-SDO")
                print("Initializing ADS7253...")
            else:
                print("Reopening FTDI/ADS7253 after invalid sample...")
            spi_ctrl.configure(args.url, frequency=args.freq)
            spi_port = spi_ctrl.get_port(0, freq=args.freq, mode=args.mode)
            ads = ADS7253Controller(spi_port)
            if not ads.write_cfr():
                raise IOError('failed to configure ADS7253 CFR')

        def read_sample_with_retries():
            last_error = None
            for attempt in range(1, args.adc_retries + 2):
                try:
                    code_a, code_b = ads.read_channels()
                    if code_a is None:
                        raise IOError('ADS7253 read returned no sample')
                    if ads.last_raw in INVALID_RAW_FRAMES:
                        raise IOError(f'invalid raw frame 0x{ads.last_raw:08X}')
                    return code_a, code_b
                except Exception as exc:
                    last_error = exc
                    if attempt > args.adc_retries:
                        break
                    print(f"  ADC sample retry {attempt}/{args.adc_retries}: {exc}", file=sys.stderr)
                    open_ads_connection()
                    if args.retry_delay:
                        time.sleep(args.retry_delay)
            raise last_error

        open_ads_connection(announce=True)

        print(
            f"Reading one sample every {args.sample_interval:.6f}s "
            f"for {args.sample_period:.3f}s")
        print(f"Saving readings to: {args.output}")

        sample_count = 0
        start_time = time.time()
        next_sample_time = start_time

        with open(args.output, 'w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow([
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

            while True:
                now = time.time()
                if now - start_time >= args.sample_period:
                    break

                if now < next_sample_time:
                    time.sleep(next_sample_time - now)

                sample_time = time.time() - start_time
                if sample_time >= args.sample_period:
                    break

                try:
                    code_a, code_b = read_sample_with_retries()
                except Exception as exc:
                    print(f"Failed to read ADS7253 sample: {exc}", file=sys.stderr)
                    return 3

                volt_a = ads.code_to_voltage(code_a)
                ac_a = ads.code_to_ac(code_a)
                volt_b = ads.code_to_voltage(code_b)
                ac_b = ads.code_to_ac(code_b)
                raw_hex = ' '.join(f'{b:02X}' for b in ads.last_rx)
                sample_count += 1

                writer.writerow([
                    sample_count,
                    f'{sample_time:.6f}',
                    code_a,
                    f'{volt_a:.6f}',
                    f'{ac_a:.6f}',
                    code_b,
                    f'{volt_b:.6f}',
                    f'{ac_b:.6f}',
                    raw_hex,
                ])

                if not args.quiet:
                    print(f"{sample_count}: A={volt_a:.6f}V AC={ac_a:+.6f}V | "
                          f"B={volt_b:.6f}V AC={ac_b:+.6f}V")
                if args.verbose:
                    print(f"  Raw: {raw_hex}")

                next_sample_time += args.sample_interval
                while next_sample_time < time.time():
                    next_sample_time += args.sample_interval

        elapsed = time.time() - start_time
        rate = sample_count / elapsed if elapsed else 0.0
        print(f"Captured {sample_count} samples in {elapsed:.3f}s ({rate:.1f} samples/s)")
        return 0

    except KeyboardInterrupt:
        print("\nStopped by user")
        return 130
    except Exception as exc:
        print(f"\nFailed to initialize FTDI/ADS7253: {exc}", file=sys.stderr)
        return 1
    finally:
        if spi_ctrl is not None:
            try:
                spi_ctrl.close()
            except Exception:
                pass


if __name__ == '__main__':
    raise SystemExit(main())
