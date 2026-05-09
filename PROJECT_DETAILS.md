# Smart Digital Voting Machine — Full Project Details

> **One-stop reference** for the entire project: what it does, how it's built, every file, every endpoint, every ESP32 event, and how to run it on a fresh computer.

---

## 1. Project overview

A single-laptop **AI-based digital voting machine** with face authentication and a USB-connected ESP32 booth display.

**Flow at a glance**

```
+----------------+        +----------------+         +-----------------+
| Webcam (face)  |  ───▶  |  Flask app +   |  ───▶   |  ESP32 + OLED   |
| Browser UI     |        |  SQLite DB     |  USB    |  + Buzzer       |
+----------------+        +----------------+         +-----------------+
        ▲                         │
        │                         ▼
        └────────  HTTP  ◀────  responses (JSON / HTML)
```

1. Admin registers each voter's face → 128-d encoding stored in SQLite.
2. On voting day, voter shows face → server matches against all encodings.
3. Match + not voted → session created → voter picks a candidate → vote stored.
4. Every event (login OK, login fail, already voted, vote cast, voter registered, election results, reset) is mirrored on the ESP32 OLED + buzzer.

---

## 2. Locked design decisions (from the planning round)

| Decision | Chosen option | Why |
|---|---|---|
| Tech stack | **Python 3.11 + Flask + HTML/CSS/JS** | Best face-recognition libraries (dlib), clean modern web UI, fewest moving parts |
| ESP32 link | **USB serial cable** (line-delimited JSON, `pyserial`) | Zero network setup, instantly reliable |
| Face engine | **`face_recognition` (dlib) — 128-d encodings** | ~99.4% LFW accuracy, battle-tested |
| ESP32 display | **0.96" OLED SSD1306 (I2C)** + passive buzzer | Cheap, easy to wire (4 pins), perfect for status text |
| Admin auth | **Single password from `.env`** | Simple and sufficient for a single-laptop machine |
| Candidates | **Dynamic — managed in Admin Panel** | Editable per election without touching code |
| Vote rule | **One vote per voter, enforced via `has_voted` flag** | Realistic election behavior |
| Reset | **Admin button: clear votes + reset `has_voted` flags** (voters retained) | Lets you re-run the demo without re-registering everyone |
| Database | **SQLite** (auto-created on first run, no migrations) | Zero install on another PC, fully portable |
| UI theme | **Clean white / navy** (Inter font) | Professional look |

---

## 3. Complete file structure

```
d:\Ai_Voting_Project\
├── app.py                              Flask entry — registers blueprints, inits DB + ESP32
├── config.py                           Loads .env, exposes Config + ensure_dirs()
├── requirements.txt                    Single source of truth for all Python deps
├── .env.example                        Template for the .env file (git-ignored)
├── .gitignore                          Ignores .env, .venv, data/, __pycache__
├── README.md                           Setup + usage guide
├── PROJECT_DETAILS.md                  ← this file
│
├── core/
│   ├── __init__.py
│   ├── db.py                           SQLite connection, schema init, helpers
│   ├── face.py                         encode_face() / match_face() / blob conversions
│   ├── esp32.py                        SerialBridge singleton (graceful no-op if unplugged)
│   └── auth.py                         admin_required / voter_required decorators
│
├── routes/
│   ├── __init__.py
│   ├── home.py                         Screen 1 — Home Dashboard
│   ├── admin.py                        Screen 2 — Admin Panel (login, register, voters,
│   │                                   candidates, show_results, reset, file serving)
│   ├── voter.py                        Screen 3 — Voter Face Login
│   ├── booth.py                        Screen 4 — Voting Booth + cast_vote
│   └── results.py                      Screen 5 — Live Results + JSON endpoint
│
├── templates/
│   ├── base.html                       Shared layout (navbar, flash, footer)
│   ├── home.html                       Hero + 3 cards
│   ├── admin/
│   │   ├── login.html
│   │   ├── _tabs.html                  Tab strip include
│   │   ├── dashboard.html              Register voter + Show Results + Reset
│   │   ├── voters.html                 Voters table
│   │   └── candidates.html             Add candidate + list
│   ├── voter_login.html                Webcam scan page
│   ├── booth.html                      Candidate cards
│   ├── booth_done.html                 Thank-you page
│   └── results.html                    Live chart + table
│
├── static/
│   ├── css/style.css                   White / navy theme
│   ├── js/
│   │   ├── camera.js                   Shared getUserMedia helper
│   │   ├── register.js                 Admin → Register Voter logic
│   │   ├── voter_login.js              Face scan + AJAX login
│   │   └── results.js                  3-second poll + Chart.js
│   └── img/.gitkeep
│
├── esp32/
│   ├── voting_display/voting_display.ino   Arduino sketch (OLED + buzzer + JSON parser)
│   └── README.md                       Wiring diagram + flashing steps
│
├── tests/
│   └── test_face_match.py              pytest smoke tests (auto-skipped if deps missing)
│
└── data/                               (auto-created on first run, git-ignored)
    ├── voting.db                       SQLite database
    ├── faces/                          Captured voter face PNGs
    └── candidates/                     Uploaded candidate symbol images
```

---

## 4. Database schema (SQLite — `data/voting.db`)

Created automatically by `core.db.init_db()` on first run. **No migrations to run.**

```sql
CREATE TABLE voters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    cnic            TEXT UNIQUE NOT NULL,
    face_encoding   BLOB NOT NULL,        -- 128 × float64 = 1024 bytes
    photo_path      TEXT,
    has_voted       INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT NOT NULL
);

CREATE TABLE candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    party           TEXT NOT NULL,
    symbol_path     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE votes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id        INTEGER NOT NULL REFERENCES voters(id)     ON DELETE CASCADE,
    candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    voted_at        TEXT NOT NULL
);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,
    voter_id    INTEGER,
    details     TEXT,        -- JSON string
    ts          TEXT NOT NULL
);
```

---

## 5. The 5 screens

| # | Screen | URL | What it does |
|---|---|---|---|
| 1 | Home Dashboard | `/` | Hero + 3 stat tiles + 3 navigation cards (Admin / Vote / Results) |
| 2 | Admin Panel | `/admin/*` | Login, register voters (webcam), manage voters list, manage candidates, **Show Results on ESP32**, Reset Election |
| 3 | Voter Face Login | `/voter/login` | Live webcam, **Scan My Face** button → face match → redirect or error |
| 4 | Voting Booth | `/booth` | Candidate cards, single-choice radio, confirm dialog → casts vote |
| 5 | Results Dashboard | `/results` | Live Chart.js bar chart + per-candidate table + turnout %, polled every 3 s |

---

## 6. All HTTP endpoints

| Method | URL | Auth | Purpose |
|---|---|---|---|
| GET  | `/` | — | Home dashboard |
| GET  | `/admin/login` | — | Admin login form |
| POST | `/admin/login` | — | Verify password → set `session.is_admin` |
| GET  | `/admin/logout` | — | Clear admin session |
| GET  | `/admin/dashboard` | admin | Register Voter + Show Results + Reset |
| POST | `/admin/register` | admin | Create voter (webcam capture + name + CNIC) |
| GET  | `/admin/voters` | admin | Voters list |
| POST | `/admin/voters/<id>/delete` | admin | Delete a voter |
| GET  | `/admin/candidates` | admin | Candidates list + add form |
| POST | `/admin/candidates` | admin | Add a candidate (with optional symbol upload) |
| POST | `/admin/candidates/<id>/delete` | admin | Delete a candidate |
| POST | `/admin/show_results` | admin | Push live tally + winner to ESP32 |
| POST | `/admin/reset` | admin | Clear votes, reset `has_voted` flags, send `RESET` to ESP32 |
| GET  | `/admin/file/<path>` | — | Serve images stored under `data/` (face snapshots, candidate symbols) |
| GET  | `/voter/login` | — | Voter scan page |
| POST | `/voter/login` | — | JSON `{image: dataURL}` → match result |
| GET  | `/booth/` | voter | Candidate selection grid |
| POST | `/booth/vote` | voter | Record vote, fire `VOTE_CAST`, show thank-you |
| GET  | `/results/` | — | Live results page |
| GET  | `/results/data` | — | JSON: candidates + counts + turnout |

---

## 7. ESP32 events (USB serial, line-delimited JSON @ 115200 baud)

Every event below is a single line of JSON terminated by `\n`. The Python side (`core/esp32.py`) opens the port lazily and **silently skips** sending if the ESP32 isn't plugged in, so the Flask app keeps working without hardware.

| Event | When it fires | JSON payload (example) | OLED screen | Buzzer |
|---|---|---|---|---|
| `LOGIN_OK` | Voter face matched and hasn't voted | `{"event":"LOGIN_OK","name":"John"}` | `WELCOME John` | 1 short beep |
| `LOGIN_FAIL` | No face matched (or no face detected) | `{"event":"LOGIN_FAIL"}` | `ACCESS DENIED — NOT REGISTERED` | 3 short beeps |
| `ALREADY_VOTED` | Match found but `has_voted = 1` | `{"event":"ALREADY_VOTED","name":"John"}` | `ALREADY VOTED — John` | 2 short beeps |
| `VOTE_CAST` | Voter cast a vote successfully | `{"event":"VOTE_CAST","name":"John","candidate":"X","party":"PTI","totals":{"PTI":47,"PMLN":33}}` | `VOTE ACCEPTED` + voter + party + total + per-party tally | 2 medium beeps |
| `VOTER_REGISTERED` | Admin registered a new voter (auto) | `{"event":"VOTER_REGISTERED","name":"John","total":12}` | `VOTER REGISTERED — John` + `Total voters: 12` | 1 short beep |
| `RESULTS` | Admin clicked **Display Results on ESP32** | `{"event":"RESULTS","totals":{"PTI":47,"PMLN":33},"total_votes":80,"winner":"PTI","tie":false}` | `WINNER: PTI` (large) + auto-scrolling per-party list with vote count and **percentage** (sticks ~12 s) | long–short–long fanfare |
| `RESET` | Admin reset the election | `{"event":"RESET"}` | `ELECTION RESET — Votes cleared. Voters retained.` | 1 long beep |

After 3.5 s of no events, the OLED falls back to a **summary screen** showing total votes + leading party + per-party tally.

The `RESULTS` screen handles three special cases:
- **Zero votes** → shows *"No votes yet."*
- **Tie** at the top → shows *"TIE at top!"* instead of a winner
- **More than 2 parties** → the list auto-scrolls every 1.8 seconds

---

## 8. Hardware: ESP32 + OLED + buzzer

**Parts**

| Part | Notes |
|---|---|
| ESP32 dev board (ESP-WROOM-32) | any USB variant |
| 0.96" OLED, **SSD1306**, **I2C** | 128×64, 4 pins (VCC/GND/SDA/SCL) |
| Passive piezo buzzer | 3.3 V tolerant |
| USB cable | data + power into the laptop |
| Jumper wires | M-F |

**Wiring**

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

**Arduino libraries (Library Manager → install)**

- `Adafruit SSD1306`
- `Adafruit GFX Library`
- `ArduinoJson` (v6.x)

**Flashing**

1. Plug ESP32 into laptop via USB.
2. Open `esp32/voting_display/voting_display.ino` in Arduino IDE 2.x.
3. Tools → Board → **ESP32 Dev Module**.
4. Tools → Port → pick the COM port that just appeared.
5. Click **Upload**. Wait for *"Done uploading."*.
6. Put that COM port in `.env` as `SERIAL_PORT=COM5` (or whatever it is).

> Important: the Arduino IDE Serial Monitor and the Flask app cannot share the port. Close the Serial Monitor before `python app.py`.

---

## 9. Python dependencies (single file)

All Python deps live in **`requirements.txt`**:

```
Flask==3.0.3
python-dotenv==1.0.1
Werkzeug==3.0.4
dlib-bin==19.24.6
face_recognition==1.3.0
face_recognition_models==0.3.0
numpy==1.26.4
opencv-python==4.10.0.84
Pillow==10.4.0
pyserial==3.5
pytest==8.3.3
```

**Why `dlib-bin` and not `dlib`?**
The plain `dlib` package compiles from source on install — on Windows that needs CMake + Visual C++ Build Tools and often fails. `dlib-bin` ships a prebuilt wheel for Windows / Linux / macOS, so `pip install` works out-of-the-box.

---

## 10. Running on a fresh computer

```powershell
# 1. Copy/clone the project
cd d:\Ai_Voting_Project

# 2. Create + activate venv
python -m venv .venv
.\.venv\Scripts\activate

# 3. Install all deps from the single file
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure .env
copy .env.example .env
notepad .env       # set ADMIN_PASSWORD and SERIAL_PORT

# 5. Run
python app.py
```

Open **http://localhost:5000**.

The first run auto-creates `data/voting.db`, `data/faces/`, and `data/candidates/`. **No migrations.**

> The Flask app **also runs without an ESP32**. Leave `SERIAL_PORT=` blank in `.env` and events are logged to the console only.

---

## 11. `.env` reference

```env
SECRET_KEY=change-me-to-a-long-random-string
ADMIN_PASSWORD=admin123
FACE_TOLERANCE=0.5            # lower = stricter (0.5 is a good default)
SERIAL_PORT=                  # e.g. COM5 on Windows, /dev/ttyUSB0 on Linux
SERIAL_BAUD=115200
ELECTION_TITLE=Smart Digital Voting Machine
```

---

## 12. End-to-end usage walkthrough

1. **Set admin password** in `.env` → restart `python app.py`.
2. **Open** http://localhost:5000 → click **Admin Panel** → log in.
3. **Register Voter** tab:
   - Enter name + CNIC.
   - Click **Capture** while looking at the camera → click **Save Voter**.
   - ESP32 shows `VOTER REGISTERED` with the running total + 1 beep.
   - Repeat for every voter.
4. **Candidates** tab → add at least 2 candidates (name, party, optional symbol).
5. **Voting day**:
   - Voter clicks **Cast Your Vote** on home → camera page → **Scan My Face**.
   - **Match + not voted** → ESP32 shows `WELCOME <name>` + 1 beep → voter is sent to the booth.
   - **No match** → ESP32 shows `ACCESS DENIED` + 3 beeps.
   - **Already voted** → ESP32 shows `ALREADY VOTED` + 2 beeps.
6. **Booth**: voter picks a candidate, confirms → vote stored.
   - ESP32 shows `VOTE ACCEPTED` with running per-party totals + 2 beeps.
7. **Live Results** (`/results`): anyone can watch counts update every 3 s.
8. **Show Results on ESP32** (admin button): pushes the winner + per-party % breakdown to the OLED with a fanfare. Use this to announce the result.
9. **Reset Election** (admin button): wipes votes, keeps voters registered.

---

## 13. Audit log

Every important event is also written to the `audit_log` table for traceability:

| Event written | Source |
|---|---|
| `REGISTER` | Admin creates a voter |
| `DELETE_VOTER` | Admin deletes a voter |
| `ADD_CANDIDATE` | Admin adds a candidate |
| `DELETE_CANDIDATE` | Admin deletes a candidate |
| `LOGIN_OK` | Successful face login |
| `LOGIN_FAIL` | Face login failed |
| `ALREADY_VOTED` | Match found but already voted |
| `VOTE_CAST` | Vote stored |
| `SHOW_RESULTS` | Admin pushed results to ESP32 |
| `RESET` | Admin reset election |

Inspect with any SQLite viewer:

```bash
sqlite3 data/voting.db "SELECT * FROM audit_log ORDER BY id DESC LIMIT 20;"
```

---

## 14. Why SQLite (not MySQL)

This is a **single-laptop** voting machine — one user at a time, all on `localhost`. SQLite is the right call:

- **Zero install** — built into Python, no MySQL server to set up on the other PC.
- **Zero migrations** — schema auto-created in `core/db.py`.
- **Portable** — copy `data/voting.db` to back up the entire election.
- **Plenty fast** for the load (a vote every few seconds at most).

If you ever scale to multi-machine networked voting, swap **only `core/db.py`** to MySQL — every other module talks through that file.

---

## 15. Theme reference (white / navy)

CSS variables in `static/css/style.css`:

```css
--navy-900: #0B1F3A   primary
--navy-700: #1E3A8A   accent / buttons
--navy-100: #DBEAFE   hover / soft fills
--bg:       #FFFFFF
--surface:  #F8FAFC
--text:     #0F172A
--border:   #E2E8F0
--success:  #10B981
--danger:   #EF4444
```

Inter font, generous padding, rounded-2xl cards, soft shadow `0 4px 24px rgba(15,23,42,.06)`.

---

## 16. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` fails on dlib | Install **CMake** + **VS C++ Build Tools** then re-run, or try `pip install dlib-bin --only-binary=:all:` |
| Camera permission denied | Browser settings → Site permissions → allow camera for `http://localhost:5000` |
| `getUserMedia` only works on https | This project uses `http://localhost`, which browsers treat as a secure context — works out of the box |
| ESP32 not found / wrong COM port | Device Manager → Ports (COM & LPT) → find the *USB-Serial* device → put its number in `.env` |
| ESP32 events not arriving | Make sure the Arduino IDE Serial Monitor is **closed** — the port can only be opened by one program at a time |
| "No face detected" on register | Better lighting, look directly at the camera, only one person in frame |
| Results page is empty | Add candidates first (Admin → Candidates) and cast at least one vote |

---

## 17. Verification checklist (end-to-end test plan)

1. `python -m venv .venv && .\.venv\Scripts\activate`
2. `pip install -r requirements.txt` — `import face_recognition` works.
3. `python app.py` → open http://localhost:5000. Home shows navy/white theme + 3 cards.
4. Admin login with `.env` password.
5. Register **2 voters** with the webcam — ESP32 shows `VOTER REGISTERED` + 1 beep each.
6. Add **3 candidates** with symbols.
7. **Voter Login (negative)** with unregistered face → `ACCESS DENIED` + 3 beeps.
8. **Voter Login (positive)** → redirected to booth + ESP32 `WELCOME` + 1 beep.
9. **Cast vote** → thank-you page + ESP32 `VOTE ACCEPTED` + 2 beeps.
10. **Already voted** check: same face again → `ALREADY VOTED` + 2 beeps.
11. **Show Results on ESP32** (admin) → winner displayed in large text + scrolling per-party list + fanfare.
12. **Live Results** page (`/results`) updates within 3 seconds.
13. **Reset election** → `ELECTION RESET` + 1 long beep. Re-vote should now work.
14. **Hardware-absent run**: unplug ESP32 → app still works, events logged to console.
15. `python -m pytest tests/test_face_match.py` passes.

---

## 18. Credits

- **face_recognition** — Adam Geitgey
- **dlib** — Davis King
- **Flask** — Pallets Projects
- **Chart.js** — chartjs.org
- **Adafruit SSD1306 + GFX** — Adafruit
- **ArduinoJson** — Benoît Blanchon
