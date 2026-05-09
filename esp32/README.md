# ESP32 Booth Display — Wiring & Flashing

This sketch turns an ESP32 + SSD1306 OLED + buzzer into the booth-side status display for the Smart Digital Voting Machine.

## 1. Parts list

| Part | Notes |
|---|---|
| ESP32 dev board (ESP-WROOM-32) | any USB variant |
| 0.96" OLED, **SSD1306**, **I2C** (4-pin: VCC, GND, SDA, SCL) | 128×64 |
| Passive piezo buzzer | 3.3 V tolerant |
| USB cable | data + power, plugs into laptop |
| Jumper wires | M-F |

## 2. Wiring

```
ESP32                 OLED (I2C)             Buzzer
-----                 ----------             ------
3V3   ──────────────  VCC
GND   ──────────────  GND  ────────────────  GND (-)
GPIO 21 (SDA)  ─────  SDA
GPIO 22 (SCL)  ─────  SCL
GPIO 25  ───────────────────────────────────  IN (+)
```

> If your OLED is at I2C address `0x3D` instead of `0x3C`, change `OLED_ADDR` in `voting_display.ino`.

## 3. Arduino IDE setup

1. **Install Arduino IDE 2.x** — https://www.arduino.cc/en/software
2. **Add the ESP32 board package**
   - File → Preferences → *Additional Boards Manager URLs* → add:
     `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Tools → Board → Boards Manager → search **esp32** by Espressif → Install.
3. **Install libraries** (Library Manager, `Ctrl+Shift+I`):
   - `Adafruit SSD1306`
   - `Adafruit GFX Library`
   - `ArduinoJson` (v6.x)

## 4. Flashing

1. Plug the ESP32 into the laptop via USB.
2. Open `esp32/voting_display/voting_display.ino` in Arduino IDE.
3. **Tools → Board** → *ESP32 Dev Module*.
4. **Tools → Port** → pick the COM port that just appeared. Note the number — you'll need it in `.env`.
5. Click **Upload** (right arrow icon). Wait for *"Done uploading."*.
6. Open **Serial Monitor** (top-right icon) at **115200 baud** to confirm boot. The OLED should display *"SDV booted. Waiting for host..."*.

## 5. Tell the Flask app where the ESP32 is

Edit `.env` in the project root:

```
SERIAL_PORT=COM5        # or COM3, COM4, /dev/ttyUSB0, /dev/cu.SLAB_USBtoUART
SERIAL_BAUD=115200
```

> **Important:** The Arduino IDE Serial Monitor and the Flask app cannot use the same port at the same time. Close the Serial Monitor before starting `python app.py`.

## 6. What you'll see

| Event | When it fires | OLED message | Buzzer |
|---|---|---|---|
| `LOGIN_OK` | Voter face matches and hasn't voted | `WELCOME <name>` | 1 short beep |
| `LOGIN_FAIL` | No face match | `ACCESS DENIED — NOT REGISTERED` | 3 short beeps |
| `ALREADY_VOTED` | Match found, but voter already voted | `ALREADY VOTED — <name>` | 2 short beeps |
| `VOTE_CAST` | Voter casts a vote | `VOTE ACCEPTED` + name + party + total + per-party tally | 2 medium beeps |
| `VOTER_REGISTERED` | Admin registers a new voter | `VOTER REGISTERED` + name + total voters | 1 short beep |
| `RESULTS` | Admin clicks *Display Results on ESP32* | `WINNER: <party>` (large) + per-party % breakdown (auto-scrolls every 1.8 s for ~12 s) | long-short-long fanfare |
| `RESET` | Admin resets the election | `ELECTION RESET` | 1 long beep |

After 3.5 s of no events the display falls back to a summary screen (total votes + leading party + per-party tally).
The `RESULTS` screen sticks for ~12 seconds and scrolls through every party with vote count and percentage, then drops back to the summary.

## 7. Running the system without an ESP32

Leave `SERIAL_PORT` blank in `.env`. The Flask app logs events to the console and runs normally — useful for development.
