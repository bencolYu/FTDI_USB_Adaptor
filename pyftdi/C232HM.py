"""C232HM utility module.

This module helps detect the serial device path for a C232HM USB adapter
connected to a Linux system and open it as a serial port.
"""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import serial
    from serial import SerialException
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None  # type: ignore
    SerialException = OSError
    list_ports = None  # type: ignore


C232HM_VID = 0x0403
C232HM_PID = 0x16d0
FTDI_SERIAL_DRIVER = 'ftdi_sio'


def _sysfs_usb_ids_for_tty(tty_path: str) -> Optional[Dict[str, str]]:
    """Read USB vendor/product IDs for a Linux tty device from sysfs."""
    try:
        tty_name = Path(tty_path).name
        sysfs_tty = Path('/sys/class/tty') / tty_name
        if not sysfs_tty.exists():
            return None

        device = sysfs_tty.resolve().parent
        for _ in range(6):
            vendor_file = device / 'idVendor'
            product_file = device / 'idProduct'
            if vendor_file.exists() and product_file.exists():
                return {
                    'vid': vendor_file.read_text().strip(),
                    'pid': product_file.read_text().strip(),
                    'device': tty_path,
                }
            device = device.parent
    except OSError:
        return None
    return None


def _sysfs_driver_for_tty(tty_path: str) -> Optional[str]:
    """Return the kernel driver name for a Linux tty device from sysfs."""
    try:
        tty_name = Path(tty_path).name
        sysfs_driver = Path('/sys/class/tty') / tty_name / 'device' / 'driver'
        if sysfs_driver.exists():
            return Path(sysfs_driver.resolve()).name
    except OSError:
        return None
    return None


def _matches_c232hm(port_info: 'serial.tools.list_ports_common.ListPortInfo') -> bool:
    """Return True if a pyserial port info object describes a C232HM device."""
    if getattr(port_info, 'vid', None) == C232HM_VID and getattr(port_info, 'pid', None) == C232HM_PID:
        return True
    hwid = getattr(port_info, 'hwid', '') or ''
    desc = (getattr(port_info, 'description', '') or '').upper()
    if '0403:16d0' in hwid or 'C232HM' in hwid.upper() or 'C232HM' in desc:
        return True
    return False


def find_ftdi_sio_ports() -> List[Dict[str, Optional[str]]]:
    """Return a list of serial ports bound to the Linux ftdi_sio driver."""
    ports: List[Dict[str, Optional[str]]] = []

    for tty in sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')):
        driver = _sysfs_driver_for_tty(tty)
        if driver == FTDI_SERIAL_DRIVER:
            ids = _sysfs_usb_ids_for_tty(tty)
            ports.append({
                'device': tty,
                'driver': driver,
                'vid': ids.get('vid') if ids else None,
                'pid': ids.get('pid') if ids else None,
            })

    if list_ports is not None:
        for port in list_ports.comports():
            if _matches_c232hm(port):
                driver = _sysfs_driver_for_tty(port.device)
                if driver == FTDI_SERIAL_DRIVER and not any(p['device'] == port.device for p in ports):
                    ports.append({
                        'device': port.device,
                        'driver': driver,
                        'vid': format(port.vid, '04x') if getattr(port, 'vid', None) is not None else None,
                        'pid': format(port.pid, '04x') if getattr(port, 'pid', None) is not None else None,
                    })

    return ports


def find_first_ftdi_sio_port() -> Optional[str]:
    """Return the first serial port path handled by ftdi_sio."""
    ports = find_ftdi_sio_ports()
    return ports[0]['device'] if ports else None


def open_c232hm_serial(device: Optional[str] = None,
                       baudrate: int = 115200,
                       timeout: float = 1.0,
                       use_sudo: bool = False,
                       **kwargs: Any) -> 'serial.Serial':
    """Open the C232HM serial device using pyserial.
    
    :param device: device path (auto-detected if None)
    :param baudrate: baud rate for serial communication
    :param timeout: serial port timeout in seconds
    :param use_sudo: if True, use subprocess with sudo for opening the port
    :param kwargs: additional arguments to pass to serial.Serial()
    :return: opened serial.Serial instance
    """
    if serial is None:
        raise ImportError('pyserial is required to open C232HM serial ports')

    if device is None:
        device = find_first_ftdi_sio_port()
        if device is None:
            raise IOError('No C232HM device bound to ftdi_sio was found')

    if use_sudo:
        import subprocess
        try:
            # Verify sudo access before attempting to open
            subprocess.run(['sudo', 'test', '-r', device], 
                          capture_output=True, check=True, timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise IOError(f"Unable to access '{device}' with sudo: {exc}") from exc

    try:
        ser = serial.Serial(device, baudrate=baudrate, timeout=timeout, **kwargs)
        return ser
    except (SerialException, OSError) as exc:
        if 'Permission denied' in str(exc) and not use_sudo:
            raise IOError(f"\nPermission denied opening '{device}'.\n"
                         f"Try: sudo python3 -c \"import pyftdi.C232HM; "
                         f"pyftdi.C232HM.open_c232hm_serial(use_sudo=True)\"\n"
                         f"Or add your user to the dialout group: sudo usermod -aG dialout $USER") from exc
        raise IOError(f"Unable to open serial device '{device}': {exc}") from exc


def send_command(device: Optional[str] = None,
                 command: str = 'state get',
                 baudrate: int = 115200,
                 timeout: float = 2.0,
                 line_ending: str = '\r\n',
                 retry_count: int = 3,
                 **kwargs: Any) -> str:
    """Send a command to the C232HM device and read the response.
    
    :param device: device path (auto-detected if None)
    :param command: command to send (default: "state get")
    :param baudrate: baud rate for serial communication
    :param timeout: serial port timeout in seconds
    :param line_ending: line ending to use (\r\n, \n, or \r)
    :param retry_count: number of times to retry if no response
    :param kwargs: additional arguments to pass to serial.Serial()
    :return: response message as string
    """
    import time
    
    try:
        ser = open_c232hm_serial(device, baudrate=baudrate, timeout=timeout, **kwargs)
    except IOError as exc:
        raise IOError(f"Failed to open serial port: {exc}") from exc

    try:
        # Clear input buffer
        print('Clearing input buffer...')
        ser.reset_input_buffer()
        
        for attempt in range(retry_count):
            print(f'\nAttempt {attempt + 1}/{retry_count}')
            
            # Send the command with line ending
            cmd_bytes = (command + line_ending).encode('utf-8')
            print(f'Sending: {repr(command)} (with {repr(line_ending)} ending)')
            ser.write(cmd_bytes)
            ser.flush()

            # Give the device time to process and respond
            time.sleep(0.5)

            # Read the response
            response = b''
            read_timeout_count = 0
            while read_timeout_count < 10:  # Try reading up to 10 times with timeout
                chunk = ser.read(256)
                if not chunk:
                    read_timeout_count += 1
                    continue
                response += chunk
                read_timeout_count = 0
            
            if response:
                return response.decode('utf-8', errors='ignore')
        
        raise IOError(f'No response from device after {retry_count} attempts')
    
    finally:
        ser.close()
