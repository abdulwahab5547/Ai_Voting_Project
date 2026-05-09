# Smart Digital Voting Machine

An end-to-end **AI-based digital voting system** that uses the laptop webcam to register voters' faces, authenticates voters via face recognition before allowing a vote, and mirrors every event on an **ESP32 + OLED + buzzer** so a poll worker can see and hear what is happening.

> Stack: **Python 3.11 · Flask · face_recognition (dlib) · SQLite · pyserial · ESP32 (Arduino)**

---

## What is in this project

| # | Screen | URL | Purpose |
|---|---|---|---|
| 1 | Home Dashboard | `/` | Entry point — links to all 5 screens |
| 2 | Admin Panel | `/admin` | Register voters, manage candidates, reset election |
| 3 | Voter Face Login | `/voter/login` | Live webcam scan + face authentication |
| 4 | Voting Booth | `/booth` | Cast vote after a successful login |
| 5 | Results Dashboard | `/results` | Live counts, turnout %, bar chart |

---

## 1. Prerequisites (must be installed before `pip install`)

These are **system-level** prerequisites — `pip` cannot install them.

| Software | Version | Why needed | Where to get it |
|---|---|---|---|
| **Python** | 3.10 / 3.11 / 3.12 (64-bit) | runs the app | https://www.python.org/downloads/ — tick **"Add Python to PATH"** during install |
| **CMake** | latest | only needed if `dlib-bin` install fails and pip falls back to building from source | https://cmake.org/download/ |
| **Microsoft C++ Build Tools** | 2019+ | same as above (Windows only) | https://visualstudio.microsoft.com/visual-cpp-build-tools/ — pick *"Desktop development with C++"* |
| **Webcam** | any USB / built-in | face capture | — |
| **Arduino IDE** | 2.x | flashing the ESP32 sketch | https://www.arduino.cc/en/software |
| **ESP32 board package** | latest | inside Arduino IDE | Arduino IDE → Boards Manager → search **esp32** by Espressif |

> 99% of the time the prebuilt `dlib-bin` wheel installs cleanly and you do **not** need CMake or the C++ Build Tools. Install them only if `pip install -r requirements.txt` complains about dlib.

---

## 2. Hardware (for the ESP32 booth display)

| Part | Notes |
|---|---|
| ESP32 dev board (ESP-WROOM-32) | any variant with USB |
| 0.96" OLED, **SSD1306**, **I2C** | 128×64, 4 pins |
| Passive buzzer | any 3.3V passive piezo |
| USB cable | data + power |
| Jumper wires | M-F |

**Wiring (full diagram in `esp32/README.md`):**

```
ESP32          OLED (I2C)         Buzzer
-----          ----------         ------
3V3   ────────  VCC
GND   ────────  GND ────────────  GND (-)
GPIO 21 ──────  SDA
GPIO 22 ──────  SCL
GPIO 25 ─────────────────────────  IN (+)
```

---

## 3. Python dependencies

A single file lists every Python package this project needs:

**[`requirements.txt`](requirements.txt)**

Install all of them with:

```powershell
pip install -r requirements.txt
```

> **Why `dlib-bin` and not `dlib`?**
> The plain `dlib` package compiles from source on install — on Windows that needs CMake + Visual C++ Build Tools and often fails. `dlib-bin` ships a prebuilt wheel for Windows / Linux / macOS, so `pip install` works out-of-the-box.

---

## 4. First-time setup (on a fresh computer)

```powershell
# 1. Clone or copy the project folder
cd d:\Ai_Voting_Project

# 2. Create + activate a virtual environment (recommended)
python -m venv .venv
.\.venv\Scripts\activate

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Create your .env from the template and edit values
copy .env.example .env
notepad .env

# 5. Run the app
python app.py
```

Open **http://localhost:5000** in any modern browser (Chrome / Edge / Firefox).

> The first time you run the app, the SQLite database (`data/voting.db`) and folders (`data/faces/`, `data/candidates/`) are created automatically — **no migrations to run**.

---

## 5. Why SQLite (and not MySQL)?

This is a **single-laptop** voting machine — one user at a time, all on `localhost`. SQLite is the right choice because:

- **Zero install** — built into Python, no MySQL server to set up on the other computer.
- **Zero migrations** — schema is auto-created on first run by `core/db.py`.
- **Portable** — copy `data/voting.db` to back up the entire election.
- **Plenty fast** for the load (a vote every few seconds, max).

If you ever scale to multi-machine networked voting, swap the `core/db.py` connection layer to MySQL — every other module talks through that file.

---

## 6. Using the system

### A. Set the admin password
Edit `.env`:
```
ADMIN_PASSWORD=your-strong-password
```

### B. Register voters (Admin → Register Voter tab)
1. Go to `/admin/login` → enter password.
2. Open the **Register Voter** tab.
3. Enter name + CNIC, click **Capture**, click **Save**.
4. The voter's 128-d face encoding is stored in `voters.face_encoding`.

### C. Add candidates (Admin → Candidates tab)
Add at least 2 candidates with name + party. Symbol image is optional.

### D. Voting day flow
1. Voter clicks **Cast Your Vote** on the home page.
2. Page asks for camera permission, shows a live preview.
3. Voter clicks **Scan My Face**.
4. **If matched and not voted** → ESP32 says *"WELCOME &lt;name&gt;"* + 1 beep. Voter is sent to the booth.
5. Voter picks a candidate, confirms → vote stored, ESP32 says *"VOTE OK"* + running totals + 2 beeps.
6. **If not registered** → ESP32 says *"ACCESS DENIED"* + 3 beeps.
7. **If already voted** → ESP32 says *"ALREADY VOTED"* + 2 short beeps.

### E. Live results
Anyone can open `/results` to see live counts (polled every 3 seconds) and turnout %.

### F. Show election results on the ESP32
Admin → **Display Results on ESP32** button (on the dashboard). The OLED shows the winning party in large text, then auto-scrolls through every party with their vote count and percentage. A long-short-long buzzer fanfare announces the result. The screen sticks for ~12 seconds, then returns to the summary.

### G. Reset the election
Admin → **Reset Election** button → confirm. Votes are wiped, voters keep their registration. ESP32 shows *"ELECTION RESET"*.

### H. Voter registration is also mirrored to the ESP32
Every time the admin successfully registers a new voter, the ESP32 briefly shows *"VOTER REGISTERED — &lt;name&gt;"* with the running total of registered voters. This gives the poll worker an audible / visual confirmation that the database actually accepted the new voter.

---

## 7. Flashing the ESP32

See **[`esp32/README.md`](esp32/README.md)** for full instructions.

Short version:
1. Open `esp32/voting_display/voting_display.ino` in Arduino IDE.
2. Install libraries (Library Manager): `Adafruit SSD1306`, `Adafruit GFX Library`, `ArduinoJson`.
3. Tools → Board → **ESP32 Dev Module**. Tools → Port → your COM port.
4. Click **Upload**.
5. Put that same COM port in `.env` as `SERIAL_PORT=COM5` (or whatever it is).

> The Flask app **also runs without an ESP32**. If `SERIAL_PORT` is empty or the port is unavailable, events are logged to the console and the app keeps working.

---

## 8. Running on a different computer

This project is designed to be portable. To run it on another PC:

1. Copy the entire `Ai_Voting_Project` folder.
2. Make sure that PC has Python 3.10+ and a webcam.
3. Follow **Section 4 — First-time setup** above.
4. (Optional) Plug in the ESP32 and update `SERIAL_PORT` in `.env`.

That's it — no MySQL, no extra services, no migrations.

---

## 9. Project structure

```
Ai_Voting_Project/
├── app.py                  Flask entry
├── config.py               .env loader
├── requirements.txt        all Python dependencies
├── .env.example            template for .env
│
├── core/                   business logic
│   ├── db.py               SQLite connection + auto schema init
│   ├── face.py             encode + match faces (face_recognition)
│   ├── esp32.py            serial bridge to ESP32
│   └── auth.py             admin_required / voter_required decorators
│
├── routes/                 Flask blueprints, one per screen
│   ├── home.py             Screen 1
│   ├── admin.py            Screen 2
│   ├── voter.py            Screen 3
│   ├── booth.py            Screen 4
│   └── results.py          Screen 5
│
├── templates/              Jinja2 HTML
├── static/                 CSS + JS + images
├── esp32/voting_display/   Arduino sketch
├── tests/                  pytest smoke tests
└── data/                   SQLite DB + uploaded images (auto-created)
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` fails on dlib | Install **CMake** + **VS Build Tools** (see Section 1), then re-run. Or try `pip install dlib-bin --only-binary=:all:`. |
| Camera permission denied | Browser settings → Site permissions → allow camera for `http://localhost:5000`. |
| `getUserMedia` only works on https | This project uses `http://localhost`, which browsers treat as a secure context — works out of the box. |
| ESP32 not found / wrong COM port | Open Device Manager → Ports (COM & LPT) → find the *USB-Serial* device. Put its number in `.env`. |
| "No face detected" on register | Make sure your face is well-lit and centered. Try a different angle. |
| Multiple faces detected | Only one person at a time during registration. |

---

## 11. Credits

Built with face_recognition (Adam Geitgey), dlib (Davis King), Flask (Pallets), Chart.js, Adafruit SSD1306 + GFX libraries.
