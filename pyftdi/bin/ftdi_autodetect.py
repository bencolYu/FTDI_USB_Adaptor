"""Helpers to find the FTDI cable connected to each target bus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from pyftdi.ftdi import Ftdi
from pyftdi.i2c import I2cController
from pyftdi.spi import SpiController
from pyftdi.usbtools import UsbTools


@dataclass(frozen=True)
class ProbeResult:
    url: str
    detail: str


def list_ftdi_urls(interface: int = 1) -> list[str]:
    """Return exact PyFtdi URLs for all connected FTDI devices."""
    devices = Ftdi.list_devices('ftdi:///?')
    dev_strings = UsbTools.build_dev_strings(
        'ftdi', Ftdi.VENDOR_IDS, Ftdi.PRODUCT_IDS, devices)
    suffix = f'/{interface}'
    return [url for url, _ in dev_strings if url.endswith(suffix)]


def to_7bit_i2c_address(addr: int) -> int:
    """Accept either a 7-bit or even 8-bit I2C write address."""
    if addr > 0x7F:
        if addr & 1:
            raise ValueError('Provided I2C address appears to be odd 8-bit value')
        return addr >> 1
    return addr


def _try_i2c_probe(url: str, probes: Iterable[Callable[[I2cController], str]]) -> str | None:
    ctrl = I2cController()
    try:
        ctrl.configure(url)
        for probe in probes:
            try:
                detail = probe(ctrl)
                if detail:
                    return detail
            except Exception:
                continue
    except Exception:
        return None
    finally:
        try:
            ctrl.close()
        except Exception:
            pass
    return None


def make_si5351_probe(addr: int) -> Callable[[I2cController], str]:
    i2c_addr = to_7bit_i2c_address(addr)

    def probe(ctrl: I2cController) -> str:
        port = ctrl.get_port(i2c_addr)
        data = port.read_from(0, readlen=1)
        if len(data) != 1:
            return ''
        return f'Si5351 register 0 read OK at I2C 0x{i2c_addr:02X}'

    return probe


def make_ad5245_probe(addr: int, cmd: int = 0x00) -> Callable[[I2cController], str]:
    i2c_addr = to_7bit_i2c_address(addr)

    def probe(ctrl: I2cController) -> str:
        port = ctrl.get_port(i2c_addr)
        data = port.exchange([cmd & 0xFF], 1)
        if len(data) != 1:
            return ''
        return f'AD5245 read OK at I2C 0x{i2c_addr:02X}'

    return probe


def find_i2c_url(
    probes: Iterable[Callable[[I2cController], str]],
    preferred_url: str = 'auto',
    exclude_urls: Iterable[str] = (),
) -> ProbeResult:
    """Resolve an I2C FTDI URL by probing real I2C devices."""
    if preferred_url != 'auto':
        detail = _try_i2c_probe(preferred_url, probes)
        if detail:
            return ProbeResult(preferred_url, f'explicit URL, {detail}')

    excluded = set(exclude_urls)
    urls = [url for url in list_ftdi_urls() if url not in excluded]
    failures = []
    for url in urls:
        detail = _try_i2c_probe(url, probes)
        if detail:
            return ProbeResult(url, detail)
        failures.append(url)

    if not urls:
        raise RuntimeError('No FTDI devices were found')
    raise RuntimeError(
        'Could not identify the I2C FTDI cable. Tried: ' + ', '.join(failures))


def _try_spi_probe(url: str, frequency: int) -> bool:
    ctrl = SpiController()
    try:
        ctrl.configure(url, frequency=frequency)
        port = ctrl.get_port(0, freq=frequency, mode=0)
        data = port.exchange([0x00, 0x00, 0x00, 0x00], 4, duplex=True)
        return len(data) == 4
    except Exception:
        return False
    finally:
        try:
            ctrl.close()
        except Exception:
            pass


def find_spi_url(
    preferred_url: str = 'auto',
    exclude_urls: Iterable[str] = (),
    frequency: int = 16000000,
) -> ProbeResult:
    """Resolve the SPI FTDI URL, preferring the non-I2C cable."""
    if preferred_url != 'auto':
        if _try_spi_probe(preferred_url, frequency):
            return ProbeResult(preferred_url, 'explicit URL, SPI transaction completed')

    excluded = set(exclude_urls)
    urls = [url for url in list_ftdi_urls() if url not in excluded]
    if not urls:
        raise RuntimeError('No candidate FTDI device remains for SPI')

    if len(urls) == 1:
        return ProbeResult(urls[0], 'only non-I2C FTDI cable')

    working = [url for url in urls if _try_spi_probe(url, frequency)]
    if len(working) == 1:
        return ProbeResult(working[0], 'SPI transaction completed')
    if working:
        raise RuntimeError(
            'Multiple FTDI devices passed the SPI probe: ' + ', '.join(working))
    raise RuntimeError('Could not identify the SPI FTDI cable. Tried: ' + ', '.join(urls))
