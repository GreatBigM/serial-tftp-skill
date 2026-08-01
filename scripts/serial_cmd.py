#!/usr/bin/env python3
"""Send commands to serial device and capture output.
Usage: python3 serial_cmd.py '<cmd>' [timeout] [baud]
  cmd: command to send (special: \\r for newline, \\x03 for Ctrl+C)
  timeout: seconds to wait (default: 3)
  baud: baud rate, 'auto' (default: cached/detect), or 'detect' (force re-detect)

Config subcommand:
  python3 serial_cmd.py config show              # show all cached config
  python3 serial_cmd.py config baud 921600       # set baud
  python3 serial_cmd.py config port /dev/ttyUSB1 # set port
  python3 serial_cmd.py config baud reset        # clear cache
"""
try:
    import serial  # pyserial
except ImportError:
    import serial_compat as serial  # 标准库 termios 兼容层（零依赖）

import time
import sys
import subprocess
from flash_config import resolve_baud, handle_config_subcommand, get

# ── config 子命令拦截 ──
if handle_config_subcommand(sys.argv[1:]):
    sys.exit(0)

CMD = sys.argv[1] if len(sys.argv) > 1 else ''
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 3
BAUD_ARG = sys.argv[3] if len(sys.argv) > 3 else 'auto'
MAX_CHARS = int(sys.argv[4]) if len(sys.argv) > 4 else 50000
PORT = get("port") or '/dev/ttyUSB0'

BAUD = resolve_baud(BAUD_ARG, PORT)

ser = serial.Serial(PORT, BAUD, timeout=0.1)
ser.reset_input_buffer()

if CMD == '\\r':
    ser.write(b'\r\n')
elif CMD == '\\x03':
    ser.write(b'\x03')
elif CMD:
    ser.write((CMD + '\r').encode())

output = b''
start = time.time()
while time.time() - start < WAIT:
    chunk = ser.read(4096)
    if chunk:
        output += chunk
        if len(output) > MAX_CHARS:
            output = output[-MAX_CHARS:]
    else:
        time.sleep(0.05)

ser.close()
text = output.decode('utf-8', errors='replace')
if not text.strip():
    print("(no output)")
else:
    print(text[-4000:] if len(text) > 4000 else text)
