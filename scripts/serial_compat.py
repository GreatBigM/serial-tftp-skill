#!/usr/bin/env python3
"""serial_compat.py — pyserial 兼容层（Python 标准库 termios 实现，零依赖）。

当环境没有 pyserial 时, 本模块提供与 pyserial 相同的 Serial 接口:
  Serial(port, baud, timeout) / read() / write() / in_waiting
  / reset_input_buffer() / flush() / close()

用法: 脚本 import 处改为
    try:
        import serial
    except ImportError:
        import serial_compat as serial

仅支持 Linux/POSIX（termios 是 POSIX 标准）。嵌入式开发场景均为 Linux。
"""

import os
import select
import termios
import time


class Serial:
    """pyserial 兼容串口封装（Linux termios）。"""

    def __init__(self, port=None, baudrate=115200, timeout=None, **kwargs):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._fd = None
        self._in_waiting = 0
        if port:
            self.open()

    # ─── 打开/关闭 ────────────────────────────────────────────────
    def open(self):
        """打开串口并设置 raw 模式。"""
        self._fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._apply_settings()

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _apply_settings(self):
        """设置波特率 + raw 模式（等效 stty cs8 -cstopb -parenb raw -echo）。"""
        attrs = termios.tcgetattr(self._fd)
        # 波特率映射（常见值）
        baud_map = {
            9600: termios.B9600, 19200: termios.B19200,
            38400: termios.B38400, 57600: termios.B57600,
            115200: termios.B115200, 230400: termios.B230400,
            460800: termios.B460800, 921600: termios.B921600,
            1500000: termios.B1500000 if hasattr(termios, "B1500000") else termios.B921600,
        }
        baud = baud_map.get(int(self.baudrate), termios.B115200)
        # iflag: raw（不处理换行/回车）
        attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK
                      | termios.ISTRIP | termios.INLCR | termios.IGNCR
                      | termios.ICRNL | termios.IXON)
        # oflag: raw
        attrs[1] &= ~(termios.OPOST)
        # cflag: cs8, 无校验, 1 停止位
        attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)
        attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
        # lflag: raw（不 echo，不缓冲）
        attrs[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON
                      | termios.ISIG | termios.IEXTEN)
        # 波特率
        attrs[4] = baud
        attrs[5] = baud
        # VMIN/VTIME: 超时控制（0/0 = 非阻塞读）
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)

    # ─── 读写 ─────────────────────────────────────────────────────
    @property
    def in_waiting(self):
        """可读字节数。"""
        try:
            import fcntl
            import array
            buf = array.array('i', [0])
            fcntl.ioctl(self._fd, 0x541B, buf, True)  # FIONREAD
            return buf[0]
        except Exception:
            return 0

    def read(self, size=1):
        """读 size 字节。非阻塞 + timeout 轮询（等效 pyserial 语义）。"""
        if self._fd is None:
            return b""
        start = time.time()
        buf = b""
        while len(buf) < size:
            try:
                chunk = os.read(self._fd, size - len(buf))
                if chunk:
                    buf += chunk
                    continue
            except (BlockingIOError, OSError):
                pass
            if self.timeout is not None and time.time() - start > self.timeout:
                break
            if self.timeout == 0:
                break
            # 等待可读（最多 10ms，保持低延迟）
            r, _, _ = select.select([self._fd], [], [], 0.01)
            if not r and self.timeout is None:
                continue
        return buf

    def write(self, data):
        """写数据，返回字节数。"""
        if self._fd is None:
            return 0
        if isinstance(data, str):
            data = data.encode()
        return os.write(self._fd, data)

    def flush(self):
        """清空输出缓冲（POSIX 无用户态缓冲，直接通过）。"""
        pass

    def reset_input_buffer(self):
        """清空输入缓冲。"""
        if self._fd is None:
            return
        try:
            while True:
                chunk = os.read(self._fd, 4096)
                if not chunk:
                    break
        except (BlockingIOError, OSError):
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ─── 便捷函数（pyserial.tools 兼容）────────────────────────────────
def serial_for_url(url, *args, **kwargs):
    """等效 pyserial.serial_for_url：直接返回 Serial（只支持设备路径）。"""
    return Serial(url, *args, **kwargs)
