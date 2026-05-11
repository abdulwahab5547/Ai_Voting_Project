# Smart Digital Voting Machine — Hardware Guide

This document covers everything for the ESP32 booth display: the wiring, the
required libraries, the serial protocol that Flask uses to talk to it, the
LCD layouts you'll see for every event, and the full setup procedure.

---

## 1. Bill of materials

| Item | Notes |
|---|---|
| ESP32 dev board | Any common 30/38-pin module |
| PCF8574T I²C 16×2 LCD | The blue/green 1602 with the I²C backpack soldered on the back |
| Passive or active buzzer | 5 V module or bare buzzer |
| 5 mm LED + 220 Ω resistor | Any colour |
| Jumper wires | Male-to-female recommended |
| USB cable | Data-capable; powers the ESP32 and carries serial events from the PC |

---

## 2. Wiring

All grounds are tied together. The ESP32 is powered from USB.

### 2.1 PCF8574T I²C 1602 LCD

| LCD pin | ESP32 pin | Notes |
|---|---|---|
| `GND` | `GND` | |
| `VCC` | **`VIN` / `5V`** | The backlight needs 5 V; do **not** use 3V3 |
| `SDA` | **`GPIO 21`** | I²C data |
| `SCL` | **`GPIO 22`** | I²C clock |

The backpack already has pull-ups on SDA/SCL. The default I²C address is
`0x27`; some boards use `0x3F`. If the screen stays blank after flashing,
change `#define LCD_ADDR 0x27` in
[`esp32/voting_display/voting_display.ino`](esp32/voting_display/voting_display.ino)
to `0x3F` and re-flash.

### 2.2 Buzzer

| Buzzer | ESP32 |
|---|---|
| `+` | **`GPIO 25`** |
| `−` | `GND` |

### 2.3 Status LED (with 220 Ω series resistor)

| LED | ESP32 |
|---|---|
| Anode (long leg) → 220 Ω → | **`GPIO 26`** |
| Cathode (short leg) | `GND` |

### 2.4 Pin map summary

| ESP32 GPIO | Function |
|---|---|
| `21` | LCD SDA |
| `22` | LCD SCL |
| `25` | Buzzer |
| `26` | LED |

---

## 3. Required Arduino libraries

Install via **Sketch → Include Library → Manage Libraries…**:

- **LiquidCrystal I2C** by Frank de Brabander
- **ArduinoJson** (v6.x)

The old `Adafruit_SSD1306` + `Adafruit_GFX` libraries are no longer used and
can be uninstalled if you wish.

---

## 4. Flashing the firmware

1. Open `esp32/voting_display/voting_display.ino` in the Arduino IDE.
2. Tools → Board → **ESP32 Dev Module** (or your specific board).
3. Tools → Port → pick the ESP32's COM port.
4. Upload.
5. After upload completes, open **Tools → Serial Monitor** at **115200 baud**
   to verify the firmware booted (you should see `SDV booted / Waiting host…`
   on the LCD).
6. Close the Serial Monitor before starting the Flask app — only one process
   can own the COM port.

---

## 5. Hooking it up to Flask

In `.env` (or whatever your config source is), set:

```
SERIAL_PORT=COM5         # whatever Windows assigns to your ESP32
SERIAL_BAUD=115200
```

The Flask app sends newline-delimited JSON events through
[`core/esp32.py`](core/esp32.py). If `SERIAL_PORT` is empty or the port can't
be opened, the app keeps working — events are just logged instead of sent.

---

## 6. Voting session flow

Voting is **closed** by default after a fresh install. The admin must
**enroll a face** and then **start the session** using that face.

```
   ┌─────────────────────────────────────────────────────┐
   │  1. Admin logs in with password  (/admin/login)     │
   │     → ESP32 shows "ADMIN LOGIN OK"                  │
   │                                                     │
   │  2. First time only: enroll admin face              │
   │     (/admin/face_enroll)                            │
   │                                                     │
   │  3. Click "Start Voting (Face Required)" on the     │
   │     dashboard. Face is captured and matched.        │
   │     On match → voting opens                         │
   │     → ESP32 shows "VOTING IS OPEN"                  │
   │                                                     │
   │  4. Voters log in with face (/voter/login) and      │
   │     cast votes in the booth                         │
   │                                                     │
   │  5. Admin clicks "End Voting" → voting closes       │
   │     → ESP32 shows "VOTING CLOSED"                   │
   │                                                     │
   │  6. Admin clicks "Display Results on ESP32"         │
   │     → LCD cycles winner + per-candidate breakdown   │
   └─────────────────────────────────────────────────────┘
```

While voting is closed:

- Voter face login is rejected with the message
  *"Voting has not started yet. Please wait for the admin."*
- The booth `cast_vote` endpoint also rejects, in case a voter session was
  still live when the admin closed voting.

---

## 7. Serial event protocol

Every event is one line of JSON terminated by `\n`. The firmware ignores
malformed lines.

| Event | Fields | LCD line 1 | LCD line 2 |
|---|---|---|---|
| `ADMIN_LOGIN` | — | `ADMIN LOGIN OK` | `Dashboard ready` |
| `ADMIN_FACE_FAIL` | `reason` | `ADMIN FACE FAIL` | reason / `Not recognized` |
| `VOTING_OPEN` | `admin` | `VOTING IS OPEN` | `By: <admin>` |
| `VOTING_CLOSED` | — | `VOTING CLOSED` | `Session ended` |
| `VOTE_CLOSED` | — | `VOTING CLOSED` | `Wait for admin` |
| `VOTER_REGISTERED` | `voter_id`, `name`, `total` | `REGISTERED #<id>` | `<name>` |
| `LOGIN_OK` | `voter_id`, `name` | `LOGIN OK   #<id>` | `Welcome <name>` |
| `LOGIN_FAIL` | `reason` | `LOGIN FAILED` | reason / `Not registered` |
| `ALREADY_VOTED` | `voter_id`, `name` | `ALREADY VOTED` | `#<id> <name>` |
| `VOTE_CAST` *(frame A)* | `voter_id`, `name`, `candidate`, `party`, `totals` | `VOTE OK    #<id>` | `<candidate>` |
| `VOTE_CAST` *(frame B)* | (auto-flipped after ~1.8 s) | `Party: <party>` | `Total votes: <n>` |
| `VOTE_FAIL` | `voter_id`, `reason` | `VOTE FAIL  #<id>` | reason / `Try again` |
| `RESULTS` *(cycles)* | `candidates`, `total_votes`, `winner`, `winner_party`, `tie` | `=== RESULTS ===` → `WINNER:` → `Cand i/N` | total / winner / `name: votes` |
| `RESET` | — | `ELECTION RESET` | `Votes cleared` |

When no event has been received for ~5 s the LCD falls back to the idle
screen:

| State | Line 1 | Line 2 |
|---|---|---|
| Voting open, no votes yet | ` VOTING  OPEN` | `Awaiting voter` |
| Voting open, votes cast | ` VOTING  OPEN` | `Total votes: <n>` |
| Voting closed | ` VOTING CLOSED` | `Awaiting admin` |

### LED behaviour

| Trigger | LED |
|---|---|
| `LOGIN_OK`, `VOTE_CAST`, `VOTER_REGISTERED`, `ADMIN_LOGIN`, `VOTING_OPEN`, `VOTING_CLOSED`, `RESET` | Solid on during display |
| `LOGIN_FAIL`, `ALREADY_VOTED`, `VOTE_FAIL`, `ADMIN_FACE_FAIL`, `VOTE_CLOSED` | Fast triple-blink |
| `RESULTS` | Slow pulse for ~20 s while the screen cycles |

### Buzzer patterns

| Trigger | Pattern |
|---|---|
| Success (login OK / vote OK / register) | 1–2 short beeps |
| Failure (login fail / already voted / vote fail) | 3 short beeps |
| Voting opens | 2 medium beeps |
| Voting closes | 1 long beep |
| Results announced | long-short-long fanfare |

---

## 8. Troubleshooting

**LCD backlight is on but no characters.**
The contrast trimpot on the back of the I²C backpack is way off — turn it
until characters appear. If still nothing, your address is probably `0x3F`
instead of `0x27`.

**LCD shows blocks on line 1 only.**
Same issue — adjust the contrast trimpot.

**Firmware uploads but nothing happens when Flask sends events.**
- Check the COM port in `.env` matches what Windows shows in Device Manager.
- Close the Arduino Serial Monitor — it holds the port and blocks Flask.
- Look at the Flask console: every event prints as `ESP32 >> {...}`. If it
  says "Cannot open COMx", the port is wrong or already in use.

**"No admin face enrolled yet" when starting voting.**
Go to **/admin/face_enroll** (or click *Enroll Admin Face* on the dashboard)
and capture one first.

**Voter login says "Voting has not started yet".**
Expected — start the session from the admin dashboard.

**ESP32 resets every time the buzzer beeps.**
Your USB port can't supply enough current. Use a powered USB hub or a
separate 5 V supply for the buzzer.
