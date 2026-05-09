"""USB-serial bridge to the ESP32 booth display.

Sends newline-delimited JSON events. The Flask app keeps working even when no
ESP32 is connected — `send()` is a no-op and just logs.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover
    serial = None  # type: ignore

from config import Config

log = logging.getLogger("esp32")


class SerialBridge:
    def __init__(self) -> None:
        self._port: Any = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if not Config.SERIAL_PORT:
            log.info("ESP32 disabled (SERIAL_PORT empty in .env).")
            return
        if serial is None:
            log.warning("pyserial not installed; ESP32 events will be skipped.")
            return
        try:
            self._port = serial.Serial(
                port=Config.SERIAL_PORT,
                baudrate=Config.SERIAL_BAUD,
                timeout=1,
                write_timeout=2,
            )
            log.info("ESP32 connected on %s @ %d", Config.SERIAL_PORT, Config.SERIAL_BAUD)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cannot open %s (%s). Continuing without ESP32.", Config.SERIAL_PORT, exc)
            self._port = None

    def send(self, event: str, **payload: Any) -> None:
        message = {"event": event, **payload}
        line = json.dumps(message) + "\n"
        log.info("ESP32 >> %s", message)
        if self._port is None:
            return
        with self._lock:
            try:
                self._port.write(line.encode("utf-8"))
                self._port.flush()
            except Exception as exc:  # noqa: BLE001
                log.warning("Serial write failed (%s). Marking ESP32 offline.", exc)
                self._port = None


esp32 = SerialBridge()
