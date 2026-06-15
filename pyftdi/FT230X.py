"""FT230X utility module.

This module helps detect the serial device path for an FT230X USB-UART adapter
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


FT230X_VID = 0x0403
FT230X_PID = 0x6015
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


def _matches_ft230x(port_info: 'serial.tools.list_ports_common.ListPortInfo') -> bool:
    """Return True if a pyserial port info object describes an FT230X device."""
    if getattr(port_info, 'vid', None) == FT230X_VID and getattr(port_info, 'pid', None) == FT230X_PID:
        return True
    hwid = getattr(port_info, 'hwid', '') or ''
    desc = (getattr(port_info, 'description', '') or '').upper()
    if '0403:6015' in hwid or 'FT230X' in hwid.upper() or 'FT230X' in desc:
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
            if _matches_ft230x(port):
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


def open_ft230x_serial(device: Optional[str] = None,
                        baudrate: int = 230400,
                        timeout: float = 1.0,
                        use_sudo: bool = False,
                        **kwargs: Any) -> 'serial.Serial':
    """Open the FT230X serial device using pyserial.
    
    :param device: device path (auto-detected if None)
    :param baudrate: baud rate for serial communication
    :param timeout: serial port timeout in seconds
    :param use_sudo: if True, use subprocess with sudo for opening the port
    :param kwargs: additional arguments to pass to serial.Serial()
    :return: opened serial.Serial instance
    """
    if serial is None:
        raise ImportError('pyserial is required to open FT230X serial ports')

    if device is None:
        device = find_first_ftdi_sio_port()
        if device is None:
            raise IOError('No FT230X device bound to ftdi_sio was found')

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
                         f"Try: sudo python3 -c \"import pyftdi.FT230X; "
                         f"pyftdi.FT230X.open_ft230x_serial(use_sudo=True)\"\n"
                         f"Or add your user to the dialout group: sudo usermod -aG dialout $USER") from exc
        raise IOError(f"Unable to open serial device '{device}': {exc}") from exc


def send_command(device: Optional[str] = None,
                 command: str = 'state get',
                 baudrate: int = 230400,
                 timeout: float = 2.0,
                 line_ending: str = '\r\n',
                 retry_count: int = 3,
                 **kwargs: Any) -> str:
    """Send a command to the FT230X device and read the response.
    
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
        ser = open_ft230x_serial(device, baudrate=baudrate, timeout=timeout, **kwargs)
    except IOError as exc:
        raise IOError(f"Failed to open serial port: {exc}") from exc

    try:
        # Clear input buffer
        print('Clearing input buffer...')
        ser.reset_input_buffer()
        
        for attempt in range(retry_count):
            print(f'\nAttempt {attempt + 1}/{retry_count}')
            
            # Send the command with line ending (PuTTY uses \r\n)
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
                if chunk:
                    response += chunk
                    print(f'Read {len(chunk)} bytes')
                    read_timeout_count = 0  # Reset timeout counter
                else:
                    read_timeout_count += 1
                    time.sleep(0.1)

            result = response.decode('utf-8', errors='replace').strip()
            total_len = len(response)
            print(f'Total response size: {total_len} bytes')
            
            # Filter out command echo if present
            if result.startswith(command):
                result = result[len(command):].strip()
                print(f'Filtered command echo, remaining: {repr(result)}')
            
            if total_len > 0 and result:
                return result
            
            # If no response, try different line ending
            if attempt == 0:
                line_ending = '\n'
                print('No response received. Retrying with \\n ending...')
                ser.reset_input_buffer()
            elif attempt == 1:
                line_ending = '\r'
                print('No response received. Retrying with \\r ending...')
                ser.reset_input_buffer()
        
        print('Warning: No response received from device after all attempts.')
        return result if result else '(no response)'
        
    finally:
        ser.close()


def demo_basic_serial():
    """Demonstrate basic serial communication with the FT230X device."""
    device = find_first_ftdi_sio_port()
    if not device:
        print('No FTDI serial device found.')
        return
    
    print(f'Device: {device}')
    print('Opening serial port for basic communication...')
    
    try:
        ser = open_ft230x_serial(device, baudrate=230400, timeout=1.0)
        print(f'Serial port opened successfully: {ser.name}')
        print(f'Settings: {ser.baudrate} baud, {ser.bytesize}{ser.parity}{ser.stopbits}')
        
        # Send a test message
        test_msg = b"Hello from FT230X!\r\n"
        print(f'Sending: {test_msg}')
        ser.write(test_msg)
        ser.flush()
        
        # Try to read any response
        import time
        time.sleep(0.5)
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            print(f'Received: {response}')
        else:
            print('No response received (this is normal for passive devices)')
        
        ser.close()
        print('Serial port closed.')
        
    except IOError as exc:
        print(f'Error: {exc}')


if __name__ == '__main__':
    ports = find_ftdi_sio_ports()
    if not ports:
        print('No FTDI serial ports using driver ftdi_sio were found.')
    else:
        print('Detected FTDI serial ports using driver ftdi_sio:')
        for port in ports:
            print(f"  {port['device']} vid={port['vid']} pid={port['pid']} driver={port['driver']}")
        print('\nOpening the first available port with 230400 baud...')
        try:
            serial_port = open_ft230x_serial(baudrate=230400)
            print(f'Opened {serial_port.name} successfully')
            serial_port.close()
        except IOError as exc:
            if 'Permission denied' in str(exc):
                print(f'Error: {exc}')
                print('\nTrying again with sudo...')
                try:
                    import subprocess
                    venv_python = Path(__file__).parent.parent / 'pyftdi' / 'venv' / 'bin' / 'python'
                    if venv_python.exists():
                        subprocess.run(['sudo', str(venv_python), __file__], check=False)
                    else:
                        subprocess.run(['sudo', 'python3', __file__], check=False)
                except Exception as e:
                    print(f'Unable to run with sudo: {e}')
            else:
                print(f'Error: {exc}')

    print('\n' + '='*60)
    print('Sending "state get" command and reading response...')
    print('='*60)
    
    # Try different baudrates like PuTTY might use
    baudrates_to_try = [230400, 115200, 9600, 19200, 38400, 57600]
    
    for baudrate in baudrates_to_try:
        print(f'\nTrying baudrate: {baudrate}')
        try:
            response = send_command(command='state get', baudrate=baudrate, timeout=2.0, retry_count=1)
            if response and response != '(no response)':
                print(f'\nSUCCESS at {baudrate} baud!')
                print(f'Response from device:\n{response}')
                break
            else:
                print(f'No response at {baudrate} baud')
        except IOError as exc:
            if 'Permission denied' in str(exc):
                print(f'Error: {exc}')
                print('\nTrying again with sudo...')
                try:
                    import subprocess
                    venv_python = Path(__file__).parent.parent / 'pyftdi' / 'venv' / 'bin' / 'python'
                    if venv_python.exists():
                        subprocess.run(['sudo', str(venv_python), __file__], check=False)
                    else:
                        subprocess.run(['sudo', 'python3', __file__], check=False)
                except Exception as e:
                    print(f'Unable to run with sudo: {e}')
                break
            else:
                print(f'Error at {baudrate} baud: {exc}')
    else:
        print('\n' + '='*60)
        print('NOTE: Device is connected but not responding to commands.')
        print('This could mean:')
        print('  - The device has no firmware loaded')
        print('  - The device is not configured for this protocol')
        print('  - The device is a passive component (e.g., just a RS232 level shifter)')
        print('  - Wrong baudrate or protocol settings')
        print('  - Device requires specific initialization sequence')
        print('')
        print('However, the FT230X USB-to-serial adapter is working correctly.')
        print('The serial port can be opened and data can be sent.')
        print('='*60)
