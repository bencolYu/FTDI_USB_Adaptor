#!/usr/bin/env python3
"""Sweep Si5351 CLK0 frequency, adjust AD5245, and capture ADS7253 samples.

Example:
  python3 pyftdi/bin/sweeping2.py 90000 150000 1000 1.0
  python3 pyftdi/bin/sweeping2.py 90k 150k 1k 1.0 --samples 128
"""
import argparse
import csv
import math
import sys
import time
from pathlib import Path

# Ensure the local pyftdi package in this repository is importable when running
# directly from the repository root or from the bin/ directory.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pyftdi.i2c import I2cController
from pyftdi.spi import SpiController
from ftdi_autodetect import (
    find_i2c_url,
    find_spi_url,
    make_ad5245_probe,
    make_si5351_probe,
)
from set_ads7253 import (
    ADS7253Controller,
    ADS7253_RECOMMENDED_BATCH_SIZE,
    parse_frequency as parse_spi_frequency,
)
from set_si5351 import (
    CLK0_FREQ_MAX_HZ,
    CLK0_FREQ_MIN_HZ,
    LOAD_CAP_VALUES,
    R_DIV_VALUES,
    SI5351_CLK0_CTRL,
    SI5351_LOAD_CAP_CTRL,
    SI5351_MS0,
    SI5351_OUTPUT_ENABLE_CTRL,
    SI5351_PLL_A,
    SI5351_PLL_RESET,
    choose_r_div_and_ms,
    multisynth_params,
    pll_params,
    reg_bytes,
    to_7bit_address,
)


AD5245_START_VALUE = 128
AD5245_MAX_VALUE = 190
AD5245_STEP_VALUE = 1
AD5245_DEFAULT_ADDR = 0x2C
AD5245_DEFAULT_CMD = 0x00
ADC_B_NOISE_REJECT_V = 0.40
MIN_ADC_RETRIES = 3
MIN_VALID_SAMPLE_RATIO = 0.50


def parse_frequency(value: str) -> int:
    """Parse Hz/KHz/MHz frequency values."""
    text = value.strip().lower()
    try:
        if text.endswith('mhz'):
            return int(float(text[:-3]) * 1_000_000)
        if text.endswith('khz'):
            return int(float(text[:-3]) * 1_000)
        if text.endswith('hz'):
            return int(float(text[:-2]))
        if text.endswith('m'):
            return int(float(text[:-1]) * 1_000_000)
        if text.endswith('k'):
            return int(float(text[:-1]) * 1_000)
        return int(float(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid frequency value: '{value}'") from exc


def parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid numeric value: '{value}'") from exc


def frequency_points(start_hz: int, stop_hz: int, step_hz: int) -> list[int]:
    if step_hz <= 0:
        raise ValueError('frequency interval must be positive')
    if start_hz > stop_hz:
        raise ValueError('start frequency must be less than or equal to stop frequency')
    points = []
    freq = start_hz
    while freq <= stop_hz:
        points.append(freq)
        freq += step_hz
    if points[-1] != stop_hz:
        points.append(stop_hz)
    return points


def validate_sweep_frequency(freq_hz: int) -> None:
    if not CLK0_FREQ_MIN_HZ <= freq_hz <= CLK0_FREQ_MAX_HZ:
        raise ValueError(
            f'frequency {freq_hz} Hz is out of range; allowed range is '
            f'{CLK0_FREQ_MIN_HZ} Hz to {CLK0_FREQ_MAX_HZ} Hz')


def write_register(port, reg_addr: int, value: int) -> None:
    port.write([reg_addr, value])


def write_block(port, reg_addr: int, values: list[int]) -> None:
    for offset, value in enumerate(values):
        write_register(port, reg_addr + offset, value)


def configure_si5351_clk0(port, freq_hz: int, load_pf: int) -> None:
    """Configure Si5351 CLK0 for one sweep frequency."""
    validate_sweep_frequency(freq_hz)
    r_div, ms, div_by_4 = choose_r_div_and_ms(float(freq_hz))
    p1_pll, p2_pll, p3_pll = pll_params(36, 0, 1)
    ms_int, ms_num, ms_den = multisynth_params(ms)
    p1_ms, p2_ms, p3_ms = pll_params(ms_int, ms_num, ms_den)

    write_register(port, SI5351_LOAD_CAP_CTRL, LOAD_CAP_VALUES[load_pf])
    write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0xFF)
    write_block(port, SI5351_PLL_A, reg_bytes(p1_pll, p2_pll, p3_pll))
    write_block(
        port,
        SI5351_MS0,
        reg_bytes(p1_ms, p2_ms, p3_ms, R_DIV_VALUES.index(r_div), div_by_4),
    )
    write_register(port, SI5351_CLK0_CTRL, 0x0F)
    write_register(port, SI5351_PLL_RESET, 0xAC)
    write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0xFE)


def rms(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))


def set_si5351_frequency(url: str, addr: int, freq_hz: int, load_pf: int) -> None:
    ctrl = I2cController()
    try:
        ctrl.configure(url)
        port = ctrl.get_port(addr)
        configure_si5351_clk0(port, freq_hz, load_pf)
    finally:
        ctrl.close()


def disable_si5351_outputs(url: str, addr: int) -> None:
    ctrl = I2cController()
    try:
        ctrl.configure(url)
        port = ctrl.get_port(addr)
        write_register(port, SI5351_OUTPUT_ENABLE_CTRL, 0xFF)
    finally:
        ctrl.close()


def set_ad5245_value(url: str, addr: int, cmd: int, value: int) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError('AD5245 value must be 0-255')
    ctrl = I2cController()
    try:
        ctrl.configure(url)
        port = ctrl.get_port(addr)
        port.write([cmd, value])
    finally:
        ctrl.close()


def read_ad5245_value(url: str, addr: int, cmd: int) -> int:
    ctrl = I2cController()
    try:
        ctrl.configure(url)
        port = ctrl.get_port(addr)
        data = port.exchange([cmd], 1)
        if len(data) != 1:
            raise IOError('AD5245 readback returned no data')
        return int(data[0])
    finally:
        ctrl.close()


def open_ads7253(url: str, spi_freq: int, spi_mode: int):
    ctrl = SpiController()
    try:
        ctrl.configure(url, frequency=spi_freq)
        spi_port = ctrl.get_port(0, freq=spi_freq, mode=spi_mode)
        ads = ADS7253Controller(spi_port)
        if not ads.write_cfr():
            raise IOError('failed to configure ADS7253 CFR')
        return ctrl, ads
    except Exception:
        ctrl.close()
        raise


def has_invalid_adc_frame(samples) -> bool:
    return any(raw == 0xFFFFFFFF for _code_a, _code_b, _rx_data, raw in samples)


def capture_ads_samples(url: str, spi_freq: int, spi_mode: int,
                        sample_count: int, batch_size: int,
                        retries: int, retry_delay: float):
    last_error = None
    for attempt in range(1, retries + 2):
        spi_ctrl = None
        try:
            spi_ctrl, ads = open_ads7253(url, spi_freq, spi_mode)
            captured = []
            remaining = sample_count
            while remaining:
                count = min(batch_size, remaining)
                try:
                    samples = ads.read_channels_batch(count)
                except Exception as exc:
                    raise IOError(f'ADS7253 read failed at batch size {count}: {exc}') from exc
                if len(samples) != count:
                    raise IOError(f'expected {count} ADC samples, got {len(samples)}')
                captured.extend(samples)
                remaining -= count
            if has_invalid_adc_frame(captured):
                raise IOError('ADS7253 returned invalid all-FF frame')
            return captured
        except Exception as exc:
            last_error = exc
            if attempt > retries:
                break
            print(
                f'    ADC capture retry {attempt}/{retries}: {exc}',
                file=sys.stderr)
            if retry_delay:
                time.sleep(retry_delay)
        finally:
            if spi_ctrl is not None:
                spi_ctrl.close()
    raise last_error


def calculate_capture(samples, sweep_start: float, total_samples_start: int):
    ads_for_conversion = ADS7253Controller(None)
    rows = []
    voltages_a = []
    voltages_b = []
    ac_values_a = []
    ac_values_b = []
    total_samples = total_samples_start
    for sample_index, (code_a, code_b, rx_data, raw) in enumerate(samples, start=1):
        total_samples += 1
        sample_time = time.time() - sweep_start
        voltage_a = ads_for_conversion.code_to_voltage(code_a)
        voltage_b = ads_for_conversion.code_to_voltage(code_b)
        ac_a = ads_for_conversion.code_to_ac(code_a)
        ac_b = ads_for_conversion.code_to_ac(code_b)
        rows.append({
            'sample': sample_index,
            'timestamp_s': sample_time,
            'code_a': code_a,
            'voltage_a_v': voltage_a,
            'ac_a_v': ac_a,
            'code_b': code_b,
            'voltage_b_v': voltage_b,
            'ac_b_v': ac_b,
            'raw_hex': ' '.join(f'{byte:02X}' for byte in rx_data),
        })
        if voltage_b > ADC_B_NOISE_REJECT_V:
            continue
        voltages_a.append(voltage_a)
        voltages_b.append(voltage_b)
        ac_values_a.append(ac_a)
        ac_values_b.append(ac_b)
    if not voltages_a:
        raise IOError(
            f'all {len(samples)} samples were rejected by voltage_b_v <= '
            f'{ADC_B_NOISE_REJECT_V:.2f} V filter')
    min_valid_samples = max(1, math.ceil(len(samples) * MIN_VALID_SAMPLE_RATIO))
    if len(voltages_a) < min_valid_samples:
        raise IOError(
            f'only {len(voltages_a)} of {len(samples)} samples passed '
            f'voltage_b_v <= {ADC_B_NOISE_REJECT_V:.2f} V filter; '
            f'minimum is {min_valid_samples}')
    stats = {
        'raw_samples': len(samples),
        'samples': len(voltages_a),
        'filtered_samples': len(samples) - len(voltages_a),
        'mean_a_v': sum(voltages_a) / len(voltages_a),
        'rms_a_v': rms(voltages_a),
        'ac_rms_a_v': rms(ac_values_a),
        'min_a_v': min(voltages_a),
        'max_a_v': max(voltages_a),
        'mean_b_v': sum(voltages_b) / len(voltages_b),
        'rms_b_v': rms(voltages_b),
        'ac_rms_b_v': rms(ac_values_b),
        'min_b_v': min(voltages_b),
        'max_b_v': max(voltages_b),
        'total_samples': total_samples,
    }
    return rows, stats


def capture_and_calculate(url: str, spi_freq: int, spi_mode: int,
                          sample_count: int, batch_size: int,
                          retries: int, retry_delay: float,
                          sweep_start: float, total_samples: int):
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            samples = capture_ads_samples(
                url, spi_freq, spi_mode, sample_count, batch_size,
                retries, retry_delay)
            return calculate_capture(samples, sweep_start, total_samples)
        except Exception as exc:
            last_error = exc
            if attempt > retries:
                break
            print(
                f'    ADC filtered capture retry {attempt}/{retries}: {exc}',
                file=sys.stderr)
            if retry_delay:
                time.sleep(retry_delay)
    raise last_error


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Sweep Si5351 CLK0, tune AD5245, and capture ADS7253 data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python3 pyftdi/bin/sweeping2.py 90000 150000 1000 1.0
  python3 pyftdi/bin/sweeping2.py 90k 150k 1k 1.0 --samples 128

Frequency range is limited to {CLK0_FREQ_MIN_HZ} Hz - {CLK0_FREQ_MAX_HZ} Hz.
Each frequency captures 128 ADS7253 samples by default.
For each frequency, AD5245 starts at {AD5245_START_VALUE} and increments until
ADS7253 channel A RMS reaches piezo_volt_set or AD5245 reaches {AD5245_MAX_VALUE}.
Summary calculations ignore samples where voltage_b_v is above
{ADC_B_NOISE_REJECT_V:.2f} V; captures are retried unless at least
{MIN_VALID_SAMPLE_RATIO:.0%} of samples remain valid. Raw accepted samples are saved.
        """,
    )
    parser.add_argument('start_frequency', type=parse_frequency,
                        help='Start CLK0 frequency, e.g. 90000 or 90k')
    parser.add_argument('stop_frequency', type=parse_frequency,
                        help='Stop CLK0 frequency, e.g. 150000 or 150k')
    parser.add_argument('interval', type=parse_frequency,
                        help='Frequency step/interval, e.g. 1000 or 1k')
    parser.add_argument('piezo_volt_set', type=parse_float,
                        help='Target channel A RMS voltage threshold')
    parser.add_argument('--addr', default='0xC0',
                        help='Si5351 8-bit I2C write address (default: 0xC0)')
    parser.add_argument('--i2c-url', default='auto',
                        help='FTDI URL for I2C cable, or auto (default: auto)')
    parser.add_argument('--ad5245-addr', default=f'0x{AD5245_DEFAULT_ADDR:02X}',
                        help='AD5245 7-bit I2C address (default: 0x2C)')
    parser.add_argument('--ad5245-cmd', default=f'0x{AD5245_DEFAULT_CMD:02X}',
                        help='AD5245 command byte (default: 0x00)')
    parser.add_argument('--ad5245-start', type=int, default=AD5245_START_VALUE,
                        help=f'AD5245 starting value for each frequency (default: {AD5245_START_VALUE})')
    parser.add_argument('--ad5245-max', type=int, default=AD5245_MAX_VALUE,
                        help=f'AD5245 upper limit (default: {AD5245_MAX_VALUE})')
    parser.add_argument('--ad5245-step', type=int, default=AD5245_STEP_VALUE,
                        help=f'AD5245 increment step (default: {AD5245_STEP_VALUE})')
    parser.add_argument('--spi-url', default='auto',
                        help='FTDI URL for SPI cable, or auto (default: auto)')
    parser.add_argument('--spi-freq', type=parse_spi_frequency, default=16_000_000,
                        help='ADS7253 SPI frequency (default: 16MHz)')
    parser.add_argument('--spi-mode', type=int, choices=[0, 1, 2, 3], default=1,
                        help='ADS7253 SPI mode (default: 1)')
    parser.add_argument('--samples', type=int, default=ADS7253_RECOMMENDED_BATCH_SIZE,
                        help='ADS7253 samples per frequency (default: 128)')
    parser.add_argument('--batch-size', type=int, default=ADS7253_RECOMMENDED_BATCH_SIZE,
                        help='ADS7253 samples per FTDI USB transaction (default: 128)')
    parser.add_argument('--settle', type=float, default=0.5,
                        help='Delay after each frequency change before ADC read, seconds (default: 0.5)')
    parser.add_argument('--adc-retries', type=int, default=3,
                        help='Retry ADC capture on communication errors or invalid all-FF frames (minimum/default: 3)')
    parser.add_argument('--retry-delay', type=float, default=0.5,
                        help='Delay before retrying a failed ADC capture, seconds (default: 0.5)')
    parser.add_argument('--load', type=int, choices=sorted(LOAD_CAP_VALUES.keys()), default=8,
                        help='Si5351 crystal load capacitance in pF (default: 8)')
    parser.add_argument('--output', default='sweep2_samples.csv',
                        help='Per-sample CSV output file (default: sweep2_samples.csv)')
    parser.add_argument('--summary-output', default='sweep2_rms.csv',
                        help='Per-frequency RMS CSV output file (default: sweep2_rms.csv)')
    parser.add_argument('--stop-on-error', action='store_true',
                        help='Stop sweep on the first frequency that fails')
    args = parser.parse_args(argv)

    try:
        points = frequency_points(
            args.start_frequency, args.stop_frequency, args.interval)
        for freq_hz in points:
            validate_sweep_frequency(freq_hz)
    except ValueError as exc:
        parser.error(str(exc))
    if args.samples <= 0:
        parser.error('--samples must be positive')
    if args.batch_size <= 0:
        parser.error('--batch-size must be positive')
    if args.settle < 0:
        parser.error('--settle must be zero or positive')
    if args.adc_retries < 0:
        parser.error('--adc-retries must be zero or positive')
    if args.retry_delay < 0:
        parser.error('--retry-delay must be zero or positive')
    adc_retries = max(args.adc_retries, MIN_ADC_RETRIES)
    if args.adc_retries < MIN_ADC_RETRIES:
        print(
            f'Using {adc_retries} ADC retries; minimum is {MIN_ADC_RETRIES}',
            file=sys.stderr)
    if args.piezo_volt_set < 0:
        parser.error('piezo_volt_set must be zero or positive')
    if not 0 <= args.ad5245_start <= 255:
        parser.error('--ad5245-start must be 0-255')
    if not 0 <= args.ad5245_max <= 255:
        parser.error('--ad5245-max must be 0-255')
    if args.ad5245_start > args.ad5245_max:
        parser.error('--ad5245-start must be less than or equal to --ad5245-max')
    if args.ad5245_step <= 0:
        parser.error('--ad5245-step must be positive')

    addr = to_7bit_address(int(args.addr, 0))
    ad5245_addr = int(args.ad5245_addr, 0)
    ad5245_cmd = int(args.ad5245_cmd, 0)
    if not 0 <= ad5245_addr <= 0x7F:
        parser.error('--ad5245-addr must be a 7-bit I2C address')
    if not 0 <= ad5245_cmd <= 0xFF:
        parser.error('--ad5245-cmd must be 0-255')
    sample_file = None
    summary_file = None
    i2c_url_for_cleanup = None

    try:
        i2c_detected = find_i2c_url((
            make_si5351_probe(addr),
            make_ad5245_probe(ad5245_addr, ad5245_cmd),
        ), args.i2c_url)
        i2c_url_for_cleanup = i2c_detected.url
        print(f'Auto-selected I2C FTDI device: {i2c_detected.url} ({i2c_detected.detail})')

        spi_detected = find_spi_url(
            args.spi_url,
            exclude_urls=(i2c_detected.url,),
            frequency=args.spi_freq,
        )
        print(f'Auto-selected SPI FTDI device: {spi_detected.url} ({spi_detected.detail})')

        sample_file = open(args.output, 'w', newline='', encoding='utf-8')
        summary_file = open(args.summary_output, 'w', newline='', encoding='utf-8')
        sample_writer = csv.writer(sample_file)
        summary_writer = csv.writer(summary_file)

        sample_writer.writerow([
            'frequency_hz',
            'ad5245_value',
            'ad5245_readback',
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
        summary_writer.writerow([
            'frequency_hz',
            'piezo_volt_set',
            'initial_ad5245_value',
            'initial_ad5245_readback',
            'initial_rms_a_v',
            'ad5245_value',
            'ad5245_readback',
            'ad5245_iterations',
            'raw_samples',
            'filtered_samples',
            'samples',
            'mean_a_v',
            'rms_a_v',
            'ac_rms_a_v',
            'min_a_v',
            'max_a_v',
            'mean_b_v',
            'rms_b_v',
            'ac_rms_b_v',
            'min_b_v',
            'max_b_v',
            'status',
            'error',
        ])

        sweep_start = time.time()
        total_samples = 0
        print(f'Sweeping {len(points)} frequencies, {args.samples} samples each')
        print(f'Writing samples to {args.output}')
        print(f'Writing RMS summary to {args.summary_output}')

        for freq_hz in points:
            print(f'Frequency {freq_hz} Hz')
            voltages_a = []
            voltages_b = []
            ac_values_a = []
            ac_values_b = []
            sample_index = 0

            try:
                print('  Setting Si5351 CLK0...')
                set_si5351_frequency(i2c_detected.url, addr, freq_hz, args.load)
                if args.settle:
                    time.sleep(args.settle)

                selected_ad5245 = None
                selected_ad5245_readback = None
                selected_rows = None
                selected_stats = None
                initial_ad5245 = None
                initial_ad5245_readback = None
                initial_rms_a = None
                iterations = 0
                print(f'  Resetting AD5245 to {args.ad5245_start}...')
                set_ad5245_value(
                    i2c_detected.url, ad5245_addr, ad5245_cmd, args.ad5245_start)
                reset_readback = read_ad5245_value(
                    i2c_detected.url, ad5245_addr, ad5245_cmd)
                print(f'    AD5245 readback after reset: {reset_readback}')
                if reset_readback != args.ad5245_start:
                    raise IOError(
                        f'AD5245 reset readback mismatch: wrote '
                        f'{args.ad5245_start}, read {reset_readback}')
                if args.settle:
                    time.sleep(args.settle)
                for ad5245_value in range(
                        args.ad5245_start,
                        args.ad5245_max + 1,
                        args.ad5245_step):
                    iterations += 1
                    selected_ad5245 = ad5245_value
                    print(f'  Setting AD5245 to {ad5245_value}...')
                    set_ad5245_value(
                        i2c_detected.url, ad5245_addr, ad5245_cmd, ad5245_value)
                    selected_ad5245_readback = read_ad5245_value(
                        i2c_detected.url, ad5245_addr, ad5245_cmd)
                    print(f'    AD5245 readback: {selected_ad5245_readback}')
                    if selected_ad5245_readback != ad5245_value:
                        raise IOError(
                            f'AD5245 readback mismatch: wrote '
                            f'{ad5245_value}, read {selected_ad5245_readback}')
                    if args.settle:
                        time.sleep(args.settle)

                    print(f'  Reading {args.samples} ADS7253 samples...')
                    selected_rows, selected_stats = capture_and_calculate(
                        spi_detected.url,
                        args.spi_freq,
                        args.spi_mode,
                        args.samples,
                        args.batch_size,
                        adc_retries,
                        args.retry_delay,
                        sweep_start,
                        total_samples,
                    )
                    print(
                        f'    rms_a_v={selected_stats["rms_a_v"]:.6f} V '
                        f'(target {args.piezo_volt_set:.6f} V, '
                        f'filtered {selected_stats["filtered_samples"]} samples)')
                    if initial_ad5245 is None:
                        initial_ad5245 = ad5245_value
                        initial_ad5245_readback = selected_ad5245_readback
                        initial_rms_a = selected_stats['rms_a_v']
                    if selected_stats['rms_a_v'] >= args.piezo_volt_set:
                        break

                if selected_rows is None or selected_stats is None:
                    raise IOError('no ADS7253 samples captured')

                voltages_a = [row['voltage_a_v'] for row in selected_rows]
                voltages_b = [row['voltage_b_v'] for row in selected_rows]
                ac_values_a = [row['ac_a_v'] for row in selected_rows]
                ac_values_b = [row['ac_b_v'] for row in selected_rows]
                sample_index = selected_stats['samples']
                total_samples = selected_stats['total_samples']
                for row in selected_rows:
                    sample_writer.writerow([
                        freq_hz,
                        selected_ad5245,
                        selected_ad5245_readback,
                        row['sample'],
                        f'{row["timestamp_s"]:.6f}',
                        row['code_a'],
                        f'{row["voltage_a_v"]:.6f}',
                        f'{row["ac_a_v"]:.6f}',
                        row['code_b'],
                        f'{row["voltage_b_v"]:.6f}',
                        f'{row["ac_b_v"]:.6f}',
                        row['raw_hex'],
                    ])

                status = (
                    'ok' if selected_stats['rms_a_v'] >= args.piezo_volt_set
                    else 'below_target_at_limit')

                summary_writer.writerow([
                    freq_hz,
                    f'{args.piezo_volt_set:.6f}',
                    initial_ad5245,
                    initial_ad5245_readback,
                    f'{initial_rms_a:.6f}',
                    selected_ad5245,
                    selected_ad5245_readback,
                    iterations,
                    selected_stats['raw_samples'],
                    selected_stats['filtered_samples'],
                    selected_stats['samples'],
                    f'{selected_stats["mean_a_v"]:.6f}',
                    f'{selected_stats["rms_a_v"]:.6f}',
                    f'{selected_stats["ac_rms_a_v"]:.6f}',
                    f'{selected_stats["min_a_v"]:.6f}',
                    f'{selected_stats["max_a_v"]:.6f}',
                    f'{selected_stats["mean_b_v"]:.6f}',
                    f'{selected_stats["rms_b_v"]:.6f}',
                    f'{selected_stats["ac_rms_b_v"]:.6f}',
                    f'{selected_stats["min_b_v"]:.6f}',
                    f'{selected_stats["max_b_v"]:.6f}',
                    status,
                    '',
                ])
            except Exception as exc:
                message = str(exc)
                print(f'  Error at {freq_hz} Hz: {message}', file=sys.stderr)
                summary_writer.writerow([
                    freq_hz,
                    f'{args.piezo_volt_set:.6f}',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    sample_index,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    'error',
                    message,
                ])
                if args.stop_on_error:
                    raise
            sample_file.flush()
            summary_file.flush()

        elapsed = time.time() - sweep_start
        print(f'Done: {len(points)} frequencies, {total_samples} samples in {elapsed:.3f}s')
        return 0
    except Exception as exc:
        print(f'Sweep failed: {exc}', file=sys.stderr)
        return 1
    finally:
        if i2c_url_for_cleanup:
            try:
                print('Disabling Si5351 outputs...')
                disable_si5351_outputs(i2c_url_for_cleanup, addr)
            except Exception as exc:
                print(f'Failed to disable Si5351 outputs: {exc}', file=sys.stderr)
        if sample_file:
            sample_file.close()
        if summary_file:
            summary_file.close()


if __name__ == '__main__':
    raise SystemExit(main())
