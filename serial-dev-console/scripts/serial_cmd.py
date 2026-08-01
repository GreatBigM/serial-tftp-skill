#!/usr/bin/env python3
"""Send commands to serial device and capture output.
Usage: python3 serial_cmd.py '<cmd>' <timeout> <baud>
  cmd: command to send (special: \\r for newline, \\x03 for Ctrl+C)
  timeout: seconds to wait (default: 3)
  baud: baud rate (default: 921600, <项目>=115200)
"""
import serial
import time
import sys

CMD = sys.argv[1] if len(sys.argv) > 1 else ''
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 3
BAUD = int(sys.argv[3]) if len(sys.argv) > 3 else 921600
MAX_CHARS = int(sys.argv[4]) if len(sys.argv) > 4 else 50000

ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.1)
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
