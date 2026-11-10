# Command Reference

This document consolidates the important commands that are explicitly present in the repository source, documentation, and example scripts. It is organized by hardware device and by function so that each command can be used quickly during development, debugging, and measurement runs.

Scope note:
- This reference is based on the current workspace contents and checked-in documentation.
- Commands that are documented in source comments or README files are included as verified repository commands.
- Commands that depend on a connected FTDI device or specific board hardware are marked as requiring hardware presence and a valid USB path.

## 1. FTDI cable discovery and USB identification

### List connected FTDI devices

```bash
python3 -c "from pyftdi.usbtools import UsbTools; UsbTools.list_devices()"
```

Purpose:
- Enumerate connected FTDI USB devices so the correct URL can be selected.

Parameters:
- No arguments required.

Expected behaviour:
- Prints the FTDI device list visible to PyFtdi.

Prerequisites:
- FTDI driver libraries available for the host environment.
- FTDI device physically connected.

Common errors:
- No FTDI devices were found
- USB/driver access not available

### Use a specific FTDI URL for I2C access

```bash
python3 pyftdi/bin/set_si5351.py --url ftdi://128/1 --addr 0xC0 --freq 113000
```

Purpose:
- Force the Si5351A configuration to use a known FTDI cable URL instead of auto-detection.

Parameters:
- `--url ftdi://128/1`: explicit FTDI URL
- `--addr 0xC0`: I2C address for the Si5351A
- `--freq 113000`: target frequency in Hz

Expected behaviour:
- Configures the Si5351A on the specified FTDI device.

### Use a specific FTDI URL for SPI access

```bash
python3 pyftdi/bin/set_ads7253.py --url ftdi://ftdi:232h/1 --freq 16MHz --read 50
```

Purpose:
- Connect to a specific FTDI SPI bridge and read ADS7253 samples.

Parameters:
- `--url ftdi://ftdi:232h/1`: explicit FTDI URL
- `--freq 16MHz`: SPI clock speed
- `--read 50`: read 50 samples

Expected behaviour:
- Initializes SPI on the selected FTDI device, configures the ADS7253, and reads samples.

---

## 2. Si5351A clock generator commands

### Set frequency on CLK0

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000
```

Purpose:
- Set the Si5351A output frequency to 113 kHz on CLK0.

Parameters:
- `--addr 0xC0`: 8-bit I2C write address of the Si5351A
- `--freq 113000`: target output frequency in Hz

Expected behaviour:
- Writes the PLL and multisynth settings, resets the clock, and enables CLK0.

Common errors:
- `Failed to auto-detect I2C FTDI device`
- `I2C operation failed: ...`
- `CLK0 frequency out of range`

### Set a frequency with both CLK0 and CLK1 enabled

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk1
```

Purpose:
- Configure the same frequency on the primary output and also enable CLK1.

Parameters:
- `--clk1`: enable the second output using the same frequency settings

Expected behaviour:
- Configures PLLA/MS0 and, when requested, MS1, then enables both outputs appropriately.

### Enable/disable/toggle a clock output directly

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 enable
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 disable
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk1-ctrl toggle
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk2-ctrl enable
```

Purpose:
- Change the output state of a specific clock without altering the current frequency.

Parameters:
- `--clk0`, `--clk1-ctrl`, `--clk2-ctrl`
- action values: `enable`, `disable`, `toggle`

Expected behaviour:
- Reads the current output-enable register and modifies the target bit.

### Set frequency and control outputs in one call

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk0 enable --clk1-ctrl disable --clk2-ctrl enable
```

Purpose:
- Configure the output frequency and also adjust individual clock states in a single operation.

Expected behaviour:
- Applies the configured frequency and then overrides the default output state with the explicit per-clock actions.

### Check current output state

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output
```

Equivalent:

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-output
```

Purpose:
- Read register `0x03` and print the current output enable state.

Expected behaviour:
- Prints a raw register value and a readable interpretation such as `CLK0 enabled`.

### Check crystal health

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal
```

Purpose:
- Read register `0x00` and report `LOS_XTAL`, `LOL_A`, and `LOL_B` status.

Expected behaviour:
- Reports the bit flags for crystal and PLL lock conditions.

### Configure clock with a custom load capacitance

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 200000 --load 10 --clk0 enable --clk1-ctrl disable
```

Purpose:
- Set a target frequency and specify a 10 pF crystal load capacitance value for the Si5351A.

Parameters:
- `--load 10`: accepted values are `6`, `8`, or `10`

Expected behaviour:
- Writes the corresponding load-capacitance register and programs the frequency.

### Preview without writing hardware

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000 --clk0 enable --dry-run
```

Purpose:
- Safety preview of the register writes without modifying the hardware.

Expected behaviour:
- Prints the planned register writes to stderr instead of applying them.

### Direct control via wrapper script

```bash
./si.sh freq 113000
./si.sh freq 100000 clk0+clk1
./si.sh clk0 enable
./si.sh clk1 disable
./si.sh status
./si.sh crystal
```

Purpose:
- Provide a simplified CLI for common Si5351A tasks.

Parameters:
- `freq <Hz>`
- `clk0|clk1|clk2 enable|disable|toggle`
- `status|show`
- `crystal|check-crystal`

Expected behaviour:
- Invokes the Python script with the appropriate flags and prints the result.

---

## 3. ADS7253 ADC commands

### Communication check

```bash
python3 pyftdi/bin/set_ads7253.py --check
```

Purpose:
- Verify that the ADS7253 is reachable and can be configured over SPI.

Expected behaviour:
- Prints the configured mode, read channel codes, and the corresponding voltages and AC offsets.

### Read a fixed number of samples

```bash
python3 pyftdi/bin/set_ads7253.py --read 10
```

Purpose:
- Capture 10 ADS7253 samples.

Parameters:
- `--read 10`: number of samples to capture

Expected behaviour:
- Prints the ADC readings and returns after the requested samples are collected.

### Read with custom frequency and explicit FTDI URL

```bash
python3 pyftdi/bin/set_ads7253.py --url ftdi://ftdi:232h/1 --freq 16MHz --read 50
```

Purpose:
- Specify an FTDI URL and a custom SPI rate.

Parameters:
- `--url ...`: target FTDI device
- `--freq 16MHz`: SPI frequency
- `--read 50`: number of samples

### Save data to CSV

```bash
python3 pyftdi/bin/set_ads7253.py --read 1000 --quiet --batch-size 128 --output ads7253.csv
```

Purpose:
- Capture many samples and save them as CSV.

Parameters:
- `--read 1000`: total samples
- `--quiet`: suppress per-sample terminal prints
- `--batch-size 128`: samples per USB transaction
- `--output ads7253.csv`: output file path

Expected behaviour:
- Writes sample data to CSV while limiting terminal output for throughput.

### Read continuously

```bash
python3 pyftdi/bin/set_ads7253.py --read 0
```

Purpose:
- Run continuous capture until interrupted with `Ctrl+C`.

Parameters:
- `--read 0`: continuous mode

Expected behaviour:
- Repeats acquisition until the user stops the process.

### Read with alternate decode diagnostics

```bash
python3 pyftdi/bin/set_ads7253.py --read 10 --decode-diagnostics
```

Purpose:
- Print alternate raw-frame decodes to help debug bit alignment.

Expected behaviour:
- Shows multiple candidate decode interpretations for the raw 32-bit SPI frame.

### Set SPI mode explicitly

```bash
python3 pyftdi/bin/set_ads7253.py --read 10 --mode 1
```

Purpose:
- Use a specific SPI mode for the ADS7253 readout.

Parameters:
- `--mode 1`: SPI mode selection

Expected behaviour:
- Uses the requested clock polarity/phase combination.

---

## 4. Sweep automation commands

### Basic frequency sweep

```bash
python3 pyftdi/bin/sweeping.py 90000 150000 1000
```

Purpose:
- Sweep from 90 kHz to 150 kHz in 1 kHz steps and capture ADS7253 samples at each frequency.

Parameters:
- `start_frequency = 90000`
- `stop_frequency = 150000`
- `interval = 1000`

Expected behaviour:
- Tunes the Si5351A, captures ADS7253 samples, and writes `sweep_samples.csv` and `sweep_rms.csv` by default.

### Sweep with a custom sample count

```bash
python3 pyftdi/bin/sweeping.py 90k 150k 1k --samples 128
```

Purpose:
- Sweep the same range, but collect 128 samples per frequency instead of the default batch size.

Parameters:
- `--samples 128`

### Tune-only sweep without ADC capture

```bash
python3 pyftdi/bin/sweeping.py 90k 150k 1k 5
```

Purpose:
- Tune the Si5351A to each frequency and dwell for 5 seconds without reading the ADC.

Parameters:
- positional `dwell_seconds = 5`

Expected behaviour:
- Configures the Si5351A at each frequency and waits at that point.

### Sweep with compensation using AD5245

```bash
python3 pyftdi/bin/sweeping3.py 95000 120000 1000 1.50
```

Purpose:
- Sweep frequency while adjusting AD5245 settings and acquiring ADS7253 samples.

Parameters:
- `95000 120000 1000`: start, stop, step
- `1.50`: tuning/dwell parameter as described in the script documentation

### Sweep variant with smaller sample sets

```bash
python3 pyftdi/bin/sweeping4.py 95000 120000 1000 1.50
python3 pyftdi/bin/sweeping4.py 95k 120k 1k 1.50 --samples 10
```

Purpose:
- Another sweep implementation, optimized for single-read behavior and compact sample counts.

### Another sweep variant

```bash
python3 pyftdi/bin/sweeping5.py 70000 85000 1000 1.50
python3 pyftdi/bin/sweeping5.py 70k 85k 1k 1.50 --samples 10
```

Purpose:
- Alternate sweep implementation using a lower frequency range and a compact sample count.

### Custom sweep output files

```bash
python3 pyftdi/bin/sweeping.py 90000 150000 1000 --output sweep_custom.csv --summary-output sweep_custom_rms.csv
```

Purpose:
- Write sweep samples and summary statistics to custom file names.

Parameters:
- `--output ...`
- `--summary-output ...`

### Stop the sweep on the first error

```bash
python3 pyftdi/bin/sweeping.py 90000 150000 1000 --stop-on-error
```

Purpose:
- Abort the sweep as soon as a frequency step fails.

Expected behaviour:
- Raises the error immediately instead of continuing to later frequencies.

---

## 5. Internal FTDI device probes and auto-detection

These commands are not usually run directly, but they are the built-in verification methods used by the Python scripts.

### I2C probe logic (used by the scripts)

```bash
python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-output
```

Purpose:
- Validate that the I2C FTDI device responds to an Si5351A probe.

### SPI probe logic (used by the scripts)

```bash
python3 pyftdi/bin/set_ads7253.py --check
```

Purpose:
- Validate that the SPI FTDI device responds to the ADS7253 communication pattern.

### Custom direct sensor read call for the AD5245

This is not typically invoked directly in the repository examples, but it is implied by `make_ad5245_probe()` in `pyftdi/bin/ftdi_autodetect.py`.

---

## 6. Common operational patterns

### Basic Si5351A enablement

```bash
cd /home/bencolyu/FTDI_USB_Adaptor
./si.sh freq 113000
./si.sh status
```

### Safe preview workflow

```bash
cd /home/bencolyu/FTDI_USB_Adaptor
./si.sh freq 113000 --dry-run
./si.sh clk0 enable --dry-run
```

### ADC bring-up workflow

```bash
cd /home/bencolyu/FTDI_USB_Adaptor
python3 pyftdi/bin/set_ads7253.py --check
python3 pyftdi/bin/set_ads7253.py --read 10 --output ads7253_single_read.csv
```

### Measurement sweep workflow

```bash
cd /home/bencolyu/FTDI_USB_Adaptor
python3 pyftdi/bin/sweeping.py 90000 150000 1000 --output sweep_samples.csv --summary-output sweep_rms.csv
```

---

## 7. Command summary by device and function

### FTDI USB / cable selection
- `python3 -c "from pyftdi.usbtools import UsbTools; UsbTools.list_devices()"`
- `python3 pyftdi/bin/set_si5351.py --url ftdi://128/1 --addr 0xC0 --freq 113000`
- `python3 pyftdi/bin/set_ads7253.py --url ftdi://ftdi:232h/1 --freq 16MHz --read 50`

### Si5351A clock control
- `python3 pyftdi/bin/set_si5351.py --addr 0xC0 --freq 113000`
- `python3 pyftdi/bin/set_si5351.py --addr 0xC0 --clk0 enable`
- `python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output`
- `python3 pyftdi/bin/set_si5351.py --addr 0xC0 --check-crystal`
- `./si.sh freq 113000`
- `./si.sh clk0 enable`
- `./si.sh status`

### ADS7253 ADC capture
- `python3 pyftdi/bin/set_ads7253.py --check`
- `python3 pyftdi/bin/set_ads7253.py --read 10`
- `python3 pyftdi/bin/set_ads7253.py --read 1000 --quiet --batch-size 128 --output ads7253.csv`
- `python3 pyftdi/bin/set_ads7253.py --read 0`

### Measurement sweep automation
- `python3 pyftdi/bin/sweeping.py 90000 150000 1000`
- `python3 pyftdi/bin/sweeping.py 90k 150k 1k --samples 128`
- `python3 pyftdi/bin/sweeping.py 90k 150k 1k 5`
- `python3 pyftdi/bin/sweeping3.py 95000 120000 1000 1.50`
- `python3 pyftdi/bin/sweeping4.py 95000 120000 1000 1.50`
- `python3 pyftdi/bin/sweeping5.py 70000 85000 1000 1.50`

---

## 8. Notes on expected outputs and hardware dependence

The repository documents the command syntax and expected high-level behavior, but the actual output varies by connected hardware and FTDI device identity. For this reason:

- the commands above are repository-verified in syntax and intent
- live output content depends on hardware present, device enumeration order, and any connected board state
- successful execution requires valid FTDI USB access, correct bus wiring, and matching I2C/SPI addresses on the board

This document intentionally describes exact command-line forms already present in the project and should be treated as a developer reference, not a guarantee of a specific bench result on a different machine.
