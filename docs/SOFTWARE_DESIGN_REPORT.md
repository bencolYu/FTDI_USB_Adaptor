# Software Design and Development Report

Date: 2026-11-10
Status: Repository-based design report. This report is based on the current workspace contents and checked-in documentation only. No prior chat transcript was available in the workspace, so historical details not explicitly recorded in the repository are identified as missing information rather than guessed.

## 1. Project Overview

### 1.1 Project objectives

The repository implements a Python-based FTDI-controlled measurement and clock-tuning system built around:

- An FTDI USB bridge used as a USB-to-I2C and USB-to-SPI host
- An Si5351A clock generator configured over I2C
- An ADS7253 analog-to-digital converter configured over SPI
- Automated sweep scripts that step a frequency range and capture ADC measurements for frequency-response or calibration analysis

The codebase appears to support two primary workflows:

1. Direct clock configuration and status queries for the Si5351A
2. Frequency sweep tests that vary Si5351A output frequency and capture ADS7253 samples to evaluate a hardware response curve or tune settings such as load capacitance and an AD5245 digital potentiometer

This is most clearly visible in the script docstrings and the sweep scripts (`pyftdi/bin/set_si5351.py`, `pyftdi/bin/set_ads7253.py`, `pyftdi/bin/sweeping.py`, `pyftdi/bin/sweeping3.py`, `pyftdi/bin/sweeping4.py`, `pyftdi/bin/sweeping5.py`).

### 1.2 Hardware components and interfaces

Verified hardware components visible in source and documentation:

- FTDI USB bridge(s) using PyFtdi
  - Used for I2C and SPI bus access
  - Auto-discovery logic is implemented in `pyftdi/bin/ftdi_autodetect.py`
  - The project supports device selection by URL and auto-detection by probing I2C/SPI transactions

- Silicon Labs Si5351A clock generator
  - Controlled over I2C
  - Default I2C address used by scripts: `0xC0` (8-bit write address; software converts to 7-bit internally)
  - Key registers include:
    - `0x03` = `OUTPUT_ENABLE_CTRL`
    - `0x10` = `CLK0_CTRL`
    - `0x11` = `CLK1_CTRL`
    - `0x1A` = `PLLA`
    - `0x2A` = `MS0`
    - `0x34` = `MS1`
    - `0xB1` = `PLL_RESET`
    - `0xB7` = `LOAD_CAP_CTRL`

- AD5245 digital potentiometer
  - Controlled over I2C
  - Default address: `0x2C`
  - Used by the sweep scripts for tuning/compensation behavior, especially in `sweeping3.py`, `sweeping4.py`, and `sweeping5.py`

- Texas Instruments ADS7253 ADC
  - Controlled over SPI using FTDI
  - Documented configuration in `ADS7253 sample code.txt`
  - The code uses 16-clock single-SDO mode and a 32-bit frame layout
  - `ADS7253_CFR_VALUE = 0x8EC0` is set in `pyftdi/bin/set_ads7253.py`

### 1.3 Software environment and dependencies

Verified from repository config:

- Primary language: Python 3
- Minimum supported Python version: 3.9+ (`pyftdi/setup.py`)
- Required packages:
  - `pyusb >= 1.0.0, != 1.2.0`
  - `pyserial >= 3.0`
- Library stack:
  - `pyftdi` package in this repository
  - FTDI USB bridging provided by `pyftdi.ftdi`, `pyftdi.i2c`, `pyftdi.spi`, and `pyftdi.usbtools`

The project includes a local copy of PyFtdi in the workspace and also adds the repository root to `sys.path` when scripts are executed directly. This is visible at the top of the script files, e.g. `pyftdi/bin/set_si5351.py` and `pyftdi/bin/set_ads7253.py`.

## 2. Software Architecture

### 2.1 Overall software architecture

The software follows a layered, host-driven design:

1. Hardware-access layer
   - PyFtdi provides low-level FTDI USB access to I2C and SPI transports
   - `pyftdi/bin/ftdi_autodetect.py` provides device probing and selection

2. Device driver layer
   - `pyftdi/bin/set_si5351.py` configures the Si5351A clock generator
   - `pyftdi/bin/set_ads7253.py` configures and reads the ADS7253 ADC
   - `si.sh` wraps the Si5351A control functions for simple CLI usage

3. Automation layer
   - `pyftdi/bin/sweeping.py` captures frequency sweeps without voltage compensation
   - `pyftdi/bin/sweeping3.py`, `sweeping4.py`, `sweeping5.py` add AD5245 tuning and compensation logic

4. Documentation/support layer
   - `README_CLOCK_CONTROL.md`, `SINGLE_COMMAND_CONTROL.md`, `CLOCK_CONTROL_REFERENCE.md`, `SOLUTION_SUMMARY.md`, and `EXAMPLES.sh`
   - These documents describe commands, operational workflow, and expected usage patterns

### 2.2 Main Python modules and responsibilities

Verified responsibilities from source code:

- `pyftdi/bin/set_si5351.py`
  - `choose_r_div_and_ms()` selects R-divider and multisynth settings
  - `pll_params()` and `multisynth_params()` compute PLL and multisynth registers
  - `format_output_state()` converts register values to readable output state
  - `control_clock_output()` modifies output-enable bits for individual clock outputs
  - `main()` handles CLI configuration, I2C auto-detection, and actual register writes

- `pyftdi/bin/set_ads7253.py`
  - `ADS7253Controller.write_cfr()` writes the CFR configuration register
  - `ADS7253Controller.read_channels()` reads both ADC channels
  - `ADS7253Controller.read_channels_batch()` performs batched reads to reduce USB round-trips
  - `parse_frequency()` accepts `Hz`, `kHz`, and `MHz` input formats
  - `main()` supports command-line capture and CSV export

- `pyftdi/bin/ftdi_autodetect.py`
  - `find_i2c_url()` finds the FTDI cable used by the I2C bus
  - `find_spi_url()` finds the SPI device while excluding the I2C device
  - `make_si5351_probe()` and `make_ad5245_probe()` are device-specific probes to validate the correct cable

- `pyftdi/bin/sweeping.py`
  - Sweeps a frequency range and captures samples without AD5245 compensation

- `pyftdi/bin/sweeping3.py`
  - Sweeps frequency and adjusts AD5245 while capturing ADS7253 samples

- `pyftdi/bin/sweeping4.py`
  - Similar to `sweeping3.py` but optimized for single-sample reads and compatibility variations

- `pyftdi/bin/sweeping5.py`
  - Another sweep variant with adjusted range and single-read logic

### 2.3 Communication protocols

The project relies on the following protocols:

- USB
  - FTDI USB bridge to host PC
  - Used as transport for PyFtdi commands

- I2C
  - Si5351A frequency generator configuration and status reads
  - AD5245 digital potentiometer control
  - The code uses `I2cController` and `port.read_from()` / `port.exchange()` to access registers

- SPI
  - ADS7253 ADC communication
  - The code uses `SpiController` and `spi_port.exchange()` / `read_channels_batch()`
  - SPI mode defaults to `1` in the ADC scripts

### 2.4 Data flow and key design decisions

The design is dominated by a repeated pattern:

1. Auto-detect the FTDI I2C and SPI cables
2. Configure the Si5351A frequency and/or output-enable state
3. Capture ADC samples using the ADS7253
4. Convert raw codes to voltage and AC values
5. Write either per-sample CSV or summary RMS CSV output

Key design decisions visible in code:

- The Si5351A output is configured using a fixed PLLA value of 900 MHz for the main target range, which is then refined by `choose_r_div_and_ms()`.
- Output-enable bits are active-low in the hardware convention: `0 = enabled`, `1 = disabled`.
- Auto-detection probes real device transactions rather than assuming a static USB index, which makes the software more robust when multiple FTDI devices are connected.
- The ADS7253 code contains explicit raw-frame bit-alignment logic because frame decoding varies with the actual SPI mode and clock phase arrangement used by the FTDI MPSSE implementation.
- Batch reads are implemented to reduce USB round-trips and improve throughput, as seen in `ADS7253Controller.read_channels_batch()`.

## 3. Detailed Implementation

### 3.1 `pyftdi/bin/set_si5351.py`

This script is the central clock-control utility.

Important functions:

- `parse_int(value: str) -> int`
  - Accepts decimal, binary, and hex integer formats

- `pll_params(a: int, b: int, c: int)`
  - Computes the Si5351A PLL parameter triplet `p1`, `p2`, `p3`

- `multisynth_params(ms: float)`
  - Splits a multisynth ratio into integer and fractional parts

- `reg_bytes(p1: int, p2: int, p3: int, r_div: int = 0, div_by_4: int = 0)`
  - Encodes Si5351A register values in the format required by the hardware

- `choose_r_div_and_ms(freq_hz: float, pll_freq_hz: float = 900e6) -> tuple[int, float, int]`
  - Chooses the proper R-divider and multisynth settings for a target frequency

- `format_output_state(reg3: int) -> str`
  - Converts the `OUTPUT_ENABLE_CTRL` register value into readable text such as `CLK0 enabled`

- `control_clock_output(port, clk_num: int, action: str, current_state: int) -> int`
  - Updates the `OUTPUT_ENABLE_CTRL` register for `CLK0`, `CLK1`, or `CLK2`
  - Supports `enable`, `disable`, and `toggle`

- `main()`
  - Parses CLI arguments, detects the correct FTDI cable, configures I2C, issues register writes, and handles output status queries and dry-run mode

Hardware configuration constants in this file:

- `XTAL_FREQ = 25_000_000`
- `CLK0_FREQ_MIN_HZ = 70_000`
- `CLK0_FREQ_MAX_HZ = 150_000`
- `R_DIV_VALUES = [1, 2, 4, 8, 16, 32, 64, 128]`
- `LOAD_CAP_VALUES = {6: 0x40, 8: 0x80, 10: 0xC0}`

Important clock-register logic:

- `SI5351_OUTPUT_ENABLE_CTRL = 0x03`
- Bits are interpreted as:
  - bit 0 = `CLK0`
  - bit 1 = `CLK1`
  - bit 2 = `CLK2`
  - `0 = enabled`, `1 = disabled`

The script enables/disables output channels by writing the register value directly.

### 3.2 `pyftdi/bin/ftdi_autodetect.py`

This module centralizes the cable-selection problem.

Main functions:

- `list_ftdi_urls(interface: int = 1) -> list[str]`
  - Lists FTDI URLs visible to PyFtdi

- `make_si5351_probe(addr: int) -> Callable[[I2cController], str]`
  - Probes the I2C bus by reading a register at a target device address

- `make_ad5245_probe(addr: int, cmd: int = 0x00)`
  - Reads a simple byte from the AD5245 to validate cable selection

- `find_i2c_url()`
  - Probes the available FTDI URLs and selects the I2C cable used by the Si5351A or AD5245

- `find_spi_url()`
  - Finds the FTDI SPI cable while excluding the I2C device when both are connected

This is a significant design feature because the project depends on multiple FTDI devices being present in some configurations.

### 3.3 `pyftdi/bin/set_ads7253.py`

This script is the ADC/measurement interface.

Main classes and functions:

- `ADS7253Controller.__init__()`
  - Stores the SPI port and controller state

- `ADS7253Controller.write_cfr()`
  - Writes the ADS7253 control register value `0x8EC0`
  - Uses a four-byte, 32-clock frame in the hardware's single-SDO configuration

- `ADS7253Controller.decode_raw(raw)`
  - Decodes the raw 32-bit word into `code_a` and `code_b`
  - The implementation explicitly notes that the bit locations are different from the nominal datasheet for the FTDI mode-1 setup

- `ADS7253Controller.read_channels()`
  - Reads a single sample from channel A and B

- `ADS7253Controller.read_channels_batch(count)`
  - Queues multiple read cycles in one USB transaction for faster capture

- `ADS7253Controller.code_to_voltage(code)`
  - Converts a raw ADC code into a voltage using the 2.5 V internal reference and 5.0 V full scale

- `ADS7253Controller.code_to_ac(code)`
  - Converts the ADC code to an AC signal relative to the 2.5 V midpoint

- `parse_frequency()`
  - Handles input formats like `16MHz`, `16000000`, `16M`, etc.

Important configuration constants:

- `ADS7253_VREF = 2.5`
- `ADS7253_FULL_SCALE = 2.0 * ADS7253_VREF = 5.0` V
- `ADS7253_MID_VOLTAGE = 2.5` V
- `ADS7253_MAX_CODE = 4095.0`
- `ADS7253_CFR_VALUE = 0x8EC0`
- `ADS7253_FRAME_BYTES = 4`

Important conversion equations:

- Voltage: `code * 5.0 / 4095`
- AC value relative to midpoint: `voltage - 2.5`

The raw frame alignment logic is especially important; the code comments explicitly state this is a bring-up/debugging issue and includes multiple decode variants for diagnostics.

### 3.4 Sweep scripts

The sweep scripts are the operational automation layer. The most relevant are:

- `pyftdi/bin/sweeping.py`
  - Frequency sweep with no voltage compensation
  - Writes per-sample and per-frequency RMS CSV outputs

- `pyftdi/bin/sweeping3.py`
  - Frequency sweep with AD5245 tuning plus ADS7253 capture
  - Compensates a voltage setting while sweeping a target range

- `pyftdi/bin/sweeping4.py`
  - Another tuned sweep version, with single-read sampling semantics and compatibility wrapper logic

- `pyftdi/bin/sweeping5.py`
  - Another tuned sweep variant, using a different operating range and sample strategy

Common functions visible across these scripts:

- `frequency_points(start_hz, stop_hz, step_hz)`
  - Generates the target frequency list

- `validate_sweep_frequency(freq_hz)`
  - Enforces the allowed range: `70,000 Hz` to `150,000 Hz`

- `configure_si5351_clk0(port, freq_hz, load_pf)`
  - Writes the PLL/MS registers and output-enable state for the target clock

- `capture_ads_samples(...)`
  - Reads ADS7253 samples for a frequency point
  - Includes invalid-frame detection and retry logic

- `rms(values)`
  - Computes RMS for each captured voltage set

### 3.5 `si.sh` wrapper and examples

The shell wrapper at the repository root provides a friendly CLI interface to the Python tools.

`si.sh` supports commands such as:

- `freq <Hz>`
- `clk0 enable|disable|toggle`
- `clk1 enable|disable|toggle`
- `clk2 enable|disable|toggle`
- `status|show`
- `crystal|check-crystal`

This script translates wrapper arguments into the appropriate `pyftdi/bin/set_si5351.py` command line.

### 3.6 Hardware configuration and register settings

Verified configuration values from source:

- Si5351A I2C address: `0xC0` (default in script)
- AD5245 I2C address: `0x2C` (default in `sweeping3.py`/`sweeping4.py`/`sweeping5.py`)
- Frequency range enforced: `70,000` to `150,000` Hz at the clock-output layer
- Crystal load values: `6 pF`, `8 pF`, `10 pF` mapped to `0x40`, `0x80`, `0xC0`
- Output-enable encoding: `0 = enabled`, `1 = disabled`
- PLLA fixed at `900 MHz` for the main tuning range:
  - `choose_r_div_and_ms()` chooses the `R_DIV` and `MS` values for a target frequency
  - `pll_params()` supplies values for the Si5351A `P1`, `P2`, `P3` calculation

### 3.7 Important calculations and parameters

The project depends on several non-trivial calculations.

1. PLL and multisynth synthesis

The code computes the Si5351A parameters with:

- `pll_params(a, b, c)`
  - `p1 = 128 * a + (128 * b) // c - 512`
  - `p2 = (128 * b) % c`
  - `p3 = c`

- `multisynth_params(ms)`
  - splits the floating-point multisynth ratio into integer/fractional parts using `Fraction(...).limit_denominator(1 << 20)`

2. Output frequency selection

- `choose_r_div_and_ms(freq_hz, pll_freq_hz=900e6)` evaluates candidate `R_DIV` values and selects the option with the lowest frequency error while staying in the valid range for the Si5351A.

3. Voltage conversion for ADS7253

- `code_to_voltage(code) = (code * 5.0) / 4095`
- `code_to_ac(code) = voltage - 2.5`

4. RMS computation in sweep scripts

- `rms(values) = sqrt(sum(value^2) / len(values))`

These formulas are directly visible in the source and are therefore verified from code.

## 4. Important Execution Commands

This section lists the commands that are explicitly documented or implemented in the repository. For each, the purpose, parameters, expected behavior, and common errors are described.

### 4.1 Configure Si5351A frequency

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000
```

Purpose:
- Set the Si5351A output frequency to `113000 Hz` and enable `CLK0` at the default output state.

Parameters:
- `--addr 0xC0`: I2C address of the Si5351A
- `--freq 113000`: target frequency in Hz

Expected behavior:
- Auto-detects the FTDI I2C device, writes the clock configuration, and prints a final status line such as `SI5351A configured for 113000 Hz on CLK0`

Prerequisites:
- FTDI cable available
- I2C bus access enabled
- Correct address and device presence

Common errors:
- `Failed to auto-detect I2C FTDI device`
- `No FTDI devices were found`
- `I2C operation failed: ...`

### 4.2 Control individual clock outputs

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 enable
```

Purpose:
- Enable or disable `CLK0` without changing the current frequency.

Parameters:
- `--clk0`: accepts `enable`, `disable`, or `toggle`

Expected behavior:
- Reads the current `OUTPUT_ENABLE_CTRL` register, modifies the output-enable bit, and writes the updated value back.

Common errors:
- invalid action string
- no FTDI device found
- failed register read/write

### 4.3 Show current output state

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output
```

Purpose:
- Read the `OUTPUT_ENABLE_CTRL` register and print a human-readable state.

Expected behavior:
- Prints the raw register value and a string such as `Output state: CLK0 enabled`.

### 4.4 Check crystal status

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal
```

Purpose:
- Read register 0 and report crystal lock/loss-of-lock status.

Expected behavior:
- Prints `LOS_XTAL` and `LOL_A`/`LOL_B` state information

### 4.5 Wrapper command for embedded usage

```bash
./si.sh freq 113000
```

Purpose:
- Convenience wrapper around the Python script.

Parameters:
- `freq`: frequency value in Hz
- optional `clk0+clk1` indicates multiple outputs for the frequency config

Expected behavior:
- Invokes `pyftdi/bin/set_si5351.py --freq 113000`

### 4.6 Basic ADS7253 read test

```bash
python3 pyftdi/bin/set_ads7253.py --check
```

Purpose:
- Verify SPI communication with the ADS7253 and perform a single read.

Expected behavior:
- Configures the ADC, reads one sample, prints channel code and voltage values, and prints a success message if the device responds.

Common errors:
- `Failed to initialize FTDI/ADS7253`
- `✗ Failed to read from ADS7253`

### 4.7 Capture N ADS7253 samples

```bash
python3 pyftdi/bin/set_ads7253.py --read 10
```

Purpose:
- Read a fixed number of samples from the ADS7253.

Parameters:
- `--read 10`: number of samples to acquire
- `--output file.csv`: optional CSV file output
- `--batch-size`: number of samples per FTDI transaction

Expected behavior:
- Prints one or more channel readings and writes CSV if `--output` is used.

### 4.8 Quick sweep demonstration

```bash
python3 pyftdi/bin/sweeping.py 90000 150000 1000
```

Purpose:
- Sweep the Si5351A frequency from 90 kHz to 150 kHz in 1 kHz steps, capturing ADS7253 samples for each frequency.

Parameters:
- `start_frequency = 90000`
- `stop_frequency = 150000`
- `interval = 1000`

Expected behavior:
- Tunes CLK0 to each frequency, captures samples, and writes CSV outputs (`sweep_samples.csv` and `sweep_rms.csv` by default).

Common errors:
- frequency out of range
- invalid ADC frame
- no FTDI device found

### 4.9 Sweeping with AD5245 tuning and compensation

```bash
python3 pyftdi/bin/sweeping3.py 95000 120000 1000 1.50
```

Purpose:
- Sweep within a frequency band while adjusting AD5245 settings and capturing ADS7253 data.

Parameters:
- `95000 120000 1000`: start, stop, and step frequencies
- `1.50`: dwell or tuning parameter as documented in the script's usage text

Expected behavior:
- Repeatedly configures the clock, tunes the potentiometer, and reads samples.

### 4.10 FTDI device enumeration

```bash
python3 -c "from pyftdi.usbtools import UsbTools; UsbTools.list_devices()"
```

Purpose:
- List connected FTDI devices so that a specific URL can be selected.

Expected behavior:
- Prints the USB device list or associated FTDI URLs.

### 4.11 Dry-run validation commands

```bash
./si.sh freq 113000 --dry-run
python3 pyftdi/bin/set_si5351.py --freq 113000 --clk0 enable --dry-run
```

Purpose:
- Preview configuration changes without writing hardware registers.

Expected behavior:
- Prints the would-be register writes rather than modifying hardware state.

This is explicitly documented as safe testing in `SOLUTION_SUMMARY.md`.

## 5. Development and Debugging History

### 5.1 Available evidence in the repository

The current workspace contains the following high-value project artifacts:

- `README_CLOCK_CONTROL.md`
- `SINGLE_COMMAND_CONTROL.md`
- `CLOCK_CONTROL_REFERENCE.md`
- `SOLUTION_SUMMARY.md`
- `si.sh`
- Python scripts under `pyftdi/bin`
- `ADS7253 sample code.txt`

These indicate a project that evolved from a direct register-control approach into a more polished CLI and sweep-based automation interface.

### 5.2 Problems encountered and documented solutions

The repository evidence strongly suggests the following issues were addressed:

1. Missing individual clock output control
   - Problem: the hardware required per-clock enable/disable control beyond a simple frequency set
   - Solution: `format_output_state()` and `control_clock_output()` were added in `pyftdi/bin/set_si5351.py`
   - Result: `--clk0`, `--clk1-ctrl`, and `--clk2-ctrl` now allow direct output state adjustments

2. Multiple FTDI devices on the same system
   - Problem: auto-selection was required instead of assuming a single FTDI cable
   - Solution: `ftdi_autodetect.py` brings explicit probing logic for I2C and SPI devices
   - Result: the scripts can detect the relevant FTDI cable by trying real device transactions

3. ADC raw-frame bit alignment mismatches
   - Problem: the ADS7253 frame is not decoded as a straight datasheet bit placement for the FTDI/SPI implementation
   - Solution: `ADS7253Controller.decode_raw()` and `decode_variants()` explicitly decode the raw 32-bit word using bit shifts and support diagnostics
   - Result: code values can be aligned to the actual hardware setup

4. Invalid or all-FF ADC frames
   - Problem: the ADC occasionally returns a full `0xFFFFFFFF` read, which indicates an invalid capture
   - Solution: `capture_ads_samples()` includes invalid-frame detection and retry logic

5. USB transaction overhead during read bursts
   - Problem: repeated single-byte or single-sample reads are slow
   - Solution: `ADS7253Controller.read_channels_batch()` queues multiple reads in one FTDI transfer

### 5.3 Inferred design changes across iterations

The presence of multiple sweep variants (`sweeping.py`, `sweeping3.py`, `sweeping4.py`, `sweeping5.py`) indicates iterative tuning of the measurement and control flow.

The likely progression is:

- Initial simple sweep without compensation (`sweeping.py`)
- Addition of AD5245 compensation and more complex measurement logic (`sweeping3.py`)
- Further tuning toward lower-sample or single-read scenarios (`sweeping4.py`, `sweeping5.py`)

This is consistent with the code comments and script docstrings, but the exact sequence of lab events is not available in the current workspace.

### 5.4 Unresolved issues and missing information

The repository does not provide complete machine-verified logs for actual bench runs. As a result:

- No verified hardware measurement trace is attached
- No command output logs are present proving a live device run was successful
- No complete chronology of previous conversations is available in the workspace

Therefore, the following should be treated as repository-inferred rather than independently confirmed:

- exact bench conditions
- final optimization choices among `sweeping3.py`, `sweeping4.py`, and `sweeping5.py`
- exact final equipment state after all tests

## 6. Verification and Testing

### 6.1 Test procedures visible in the code and docs

The repository includes multiple test and validation paths:

- Dry-run register preview mode in `pyftdi/bin/set_si5351.py`
- ADC communication check mode in `pyftdi/bin/set_ads7253.py --check`
- Frequency sweep scripts with CSV output generation
- Crystal read and output enable read commands

### 6.2 Commands documented as used for verification

Verified from the documentation:

```bash
./si.sh freq 113000 --dry-run
./si.sh clk0 enable --dry-run
python3 pyftdi/bin/set_si5351.py --freq 113000 --clk0 enable --dry-run
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal
python3 pyftdi/bin/set_ads7253.py --check
python3 pyftdi/bin/sweeping.py 90000 150000 1000
```

### 6.3 Observed results and known limitations

The repository documentation explicitly states these dry-run commands are successful and generate expected register writes. This is documented in `SOLUTION_SUMMARY.md`.

However, the current workspace does not include actual hardware logs or terminal captures proving the commands were run successfully on a real board. Therefore:

- The documentation is treated as a claimed execution history, not as a fully independent verification artifact.
- The code itself is the primary source of truth for design intent.

Known limitations visible in code:

- Auto-detection depends on valid I2C/SPI transactions and requires the correct device to be present on the bus
- The scripts assume a particular clock range and specific FTDI hardware behavior
- The ADS7253 decode is sensitive to bit alignment and clock-phase assumptions
- Some sweep scripts (`sweeping3.py`, `sweeping4.py`, `sweeping5.py`) appear to be variants of the same measurement workflow rather than a single consolidated architecture

## 7. Future Improvements

### 7.1 Potential code improvements

- Consolidate overlapping frequency-sweep logic from `sweeping.py`, `sweeping3.py`, `sweeping4.py`, and `sweeping5.py` into a single reusable sweep framework
- Add a formal test suite for `pll_params()`, `reg_bytes()`, `choose_r_div_and_ms()`, and ADS7253 decode logic
- Add structured logging instead of ad hoc `print()` output
- Introduce typed configuration objects for FTDI URL, device addresses, and sweep parameters
- Improve error handling around FTDI disconnections and partial reads

### 7.2 Reliability considerations

- Device detection should be hardened for multi-cable systems by storing device identity metadata instead of relying on a single probe pattern
- Retry logic should be centralized and tied to explicit diagnosis (e.g., invalid ADC frames vs. USB disconnects)
- The ADS7253 decode should be validated across multiple SPI modes and clock-phase combinations before production use
- Sweep scripts should capture and persist hardware metadata (temperature, device URL, board revision, sample rate, clock settings) with each CSV output

### 7.3 Recommended next steps

1. Create an explicit regression test suite for the clock-configuration calculations and raw-frame decode logic.
2. Decide on one canonical sweep implementation and retire or archive experimental variants (`sweeping3.py`, `sweeping4.py`, `sweeping5.py`) if they are no longer needed.
3. Capture real bench logs from a single verified configuration and preserve them with the repository.
4. Add documentation that separates verified bench results from design intent and unverified assumptions.
5. Standardize command-line interfaces so that all scripts use a consistent flag naming and output format.

## Appendix A: Verified repository facts

This report is based on verified evidence in the current workspace:

- `pyftdi/bin/set_si5351.py` contains the clock configuration logic and register constants
- `pyftdi/bin/ftdi_autodetect.py` contains FTDI auto-detection logic
- `pyftdi/bin/set_ads7253.py` contains the SPI controller, ADC configuration, and voltage conversion logic
- `pyftdi/bin/sweeping.py` and related scripts contain the sweep automation logic
- `README_CLOCK_CONTROL.md`, `SINGLE_COMMAND_CONTROL.md`, and `SOLUTION_SUMMARY.md` describe the intended operational workflow
- `pyftdi/setup.py` confirms Python 3.9+ and the required package dependencies

## Appendix B: Explicit assumptions and missing information

The following items are not independently verifiable from the current workspace:

- Original previous conversation history
- Exact real-world hardware test logs
- Exact bench conditions used when the sweep scripts were validated
- Whether any of the later sweep variants (`sweeping3.py`, `sweeping4.py`, `sweeping5.py`) superseded the earlier ones in production use

These are explicitly treated as missing information and are not assumed in the design analysis above.
