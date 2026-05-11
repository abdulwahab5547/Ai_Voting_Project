/*
 * Smart Digital Voting Machine — ESP32 Booth Display (1602 I2C LCD)
 *
 * Hardware
 *   ESP32 dev board
 *   PCF8574T I2C 16x2 LCD on SDA = GPIO 21, SCL = GPIO 22 (5V VCC)
 *   Passive/active buzzer on GPIO 25
 *   Status LED (via 220R) on GPIO 26
 *
 * Required libraries (Library Manager):
 *   LiquidCrystal I2C   (by Frank de Brabander)
 *   ArduinoJson         (v6.x)
 *
 * Serial protocol (newline-delimited JSON from Flask):
 *   {"event":"ADMIN_LOGIN"}
 *   {"event":"ADMIN_FACE_FAIL","reason":"No match"}
 *   {"event":"VOTING_OPEN","admin":"Admin"}
 *   {"event":"VOTING_CLOSED"}
 *   {"event":"VOTE_CLOSED"}
 *   {"event":"VOTER_REGISTERED","voter_id":42,"name":"John","total":12}
 *   {"event":"LOGIN_OK","voter_id":42,"name":"John"}
 *   {"event":"LOGIN_FAIL","reason":"No match"}
 *   {"event":"ALREADY_VOTED","voter_id":42,"name":"John"}
 *   {"event":"VOTE_CAST","voter_id":42,"name":"John","candidate":"Imran","party":"PTI","totals":{"PTI":47}}
 *   {"event":"VOTE_FAIL","voter_id":42,"reason":"Already voted"}
 *   {"event":"RESULTS","candidates":{"Imran":12,"Bilawal":8},"total_votes":20,"winner":"Imran","winner_party":"PTI","tie":false}
 *   {"event":"RESET"}
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// ---- Pins / hardware -----------------------------------------------------
#define LCD_ADDR     0x27   // change to 0x3F if your PCF8574 board uses that
#define LCD_COLS     16
#define LCD_ROWS     2
#define BUZZER_PIN   25
#define LED_PIN      26
#define SDA_PIN      21
#define SCL_PIN      22

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// ---- Timing --------------------------------------------------------------
const unsigned long TRANSIENT_MS        = 5000;   // how long a flash screen lingers
const unsigned long VOTE_FRAME_MS       = 1800;   // VOTE_CAST flips between 2 frames
const unsigned long RESULTS_FRAME_MS    = 2200;   // RESULTS cycles through frames
const unsigned long RESULTS_DURATION_MS = 20000;  // total time RESULTS sticks

// ---- LED state machine ---------------------------------------------------
enum LedMode { LED_OFF_M, LED_ON_M, LED_BLINK_FAST, LED_PULSE };
LedMode       ledMode = LED_OFF_M;
unsigned long ledStartMs = 0;
unsigned long ledLastToggleMs = 0;
bool          ledLevel = false;

void ledSet(LedMode m) {
  ledMode = m;
  ledStartMs = millis();
  ledLastToggleMs = millis();
  if (m == LED_ON_M)        { digitalWrite(LED_PIN, HIGH); ledLevel = true; }
  else if (m == LED_OFF_M)  { digitalWrite(LED_PIN, LOW);  ledLevel = false; }
}

void ledTick() {
  unsigned long now = millis();
  if (ledMode == LED_BLINK_FAST) {
    if (now - ledLastToggleMs >= 120) {
      ledLevel = !ledLevel;
      digitalWrite(LED_PIN, ledLevel ? HIGH : LOW);
      ledLastToggleMs = now;
    }
    if (now - ledStartMs > 1200) ledSet(LED_OFF_M);
  } else if (ledMode == LED_PULSE) {
    if (now - ledLastToggleMs >= 500) {
      ledLevel = !ledLevel;
      digitalWrite(LED_PIN, ledLevel ? HIGH : LOW);
      ledLastToggleMs = now;
    }
  }
}

// ---- Buzzer --------------------------------------------------------------
void beep(int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    tone(BUZZER_PIN, 2000);
    delay(onMs);
    noTone(BUZZER_PIN);
    if (offMs > 0) delay(offMs);
  }
}

// ---- LCD helpers ---------------------------------------------------------
void lcdWriteLine(uint8_t row, const String& text) {
  String s = text;
  if (s.length() > LCD_COLS) s = s.substring(0, LCD_COLS);
  while (s.length() < LCD_COLS) s += ' ';
  lcd.setCursor(0, row);
  lcd.print(s);
}

void lcdShow(const String& line1, const String& line2) {
  lcdWriteLine(0, line1);
  lcdWriteLine(1, line2);
}

// Compact "#<id> <name>" into 16 chars. id may be 0 (omitted).
String idAndName(int id, const String& name) {
  String prefix = (id > 0) ? (String("#") + id + " ") : String("");
  int budget = LCD_COLS - (int)prefix.length();
  String n = name;
  if (n.length() > (unsigned)budget) n = n.substring(0, budget);
  return prefix + n;
}

// ---- Event / screen state ------------------------------------------------
enum Screen {
  SCR_IDLE,
  SCR_TRANSIENT,    // one-shot flash, returns to idle after TRANSIENT_MS
  SCR_VOTE_CAST,    // two-frame flip during transient window
  SCR_RESULTS       // cycles through frames for RESULTS_DURATION_MS
};
Screen        screen = SCR_IDLE;
unsigned long screenEnterMs = 0;
unsigned long screenLastFrameMs = 0;
int           screenFrameIdx = 0;

// VOTE_CAST cached payload
String vcName, vcCandidate, vcParty;
int    vcVoterId = 0;
int    vcTotalVotes = 0;

// RESULTS cached payload
const int  MAX_CANDS = 8;
String     resCandName[MAX_CANDS];
int        resCandVotes[MAX_CANDS];
int        resCandCount = 0;
int        resTotalVotes = 0;
String     resWinner = "";
String     resWinnerParty = "";
bool       resTie = false;

// Idle summary
int totalVotes = 0;
int totalVoters = 0;
bool votingOpen = false;

// ---- Render functions ----------------------------------------------------
void renderIdle() {
  String l1 = votingOpen ? " VOTING  OPEN" : " VOTING CLOSED";
  String l2 = totalVotes > 0
                ? (String("Total votes: ") + totalVotes)
                : (votingOpen ? String("Awaiting voter") : String("Awaiting admin"));
  lcdShow(l1, l2);
}

void renderAdminLogin() {
  lcdShow("ADMIN LOGIN OK", "Dashboard ready");
}

void renderAdminFaceFail(const String& reason) {
  lcdShow("ADMIN FACE FAIL", reason.length() ? reason : String("Not recognized"));
}

void renderVotingOpen(const String& admin) {
  String l2 = admin.length() ? (String("By: ") + admin) : String("Voters welcome");
  lcdShow("VOTING IS OPEN", l2);
}

void renderVotingClosed() {
  lcdShow("VOTING CLOSED", "Session ended");
}

void renderVoteClosed() {
  lcdShow("VOTING CLOSED", "Wait for admin");
}

void renderVoterRegistered(int id, const String& name, int total) {
  lcdShow(String("REGISTERED #") + id, idAndName(0, name));
  // total goes to idle screen later
  totalVoters = total;
}

void renderLoginOk(int id, const String& name) {
  lcdShow(String("LOGIN OK   #") + id, String("Welcome ") + name);
}

void renderLoginFail(const String& reason) {
  String r = reason.length() ? reason : String("Not registered");
  lcdShow("LOGIN FAILED", r);
}

void renderAlreadyVoted(int id, const String& name) {
  lcdShow("ALREADY VOTED", idAndName(id, name));
}

void renderVoteFail(int id, const String& reason) {
  String l1 = "VOTE FAILED";
  if (id > 0) l1 = String("VOTE FAIL  #") + id;
  lcdShow(l1, reason.length() ? reason : String("Try again"));
}

void renderVoteCastFrame(int frame) {
  if (frame % 2 == 0) {
    lcdShow(String("VOTE OK    #") + vcVoterId, vcCandidate);
  } else {
    lcdShow(String("Party: ") + vcParty, String("Total votes: ") + vcTotalVotes);
  }
}

void renderResetScreen() {
  lcdShow("ELECTION RESET", "Votes cleared");
}

// RESULTS frames:
//   0 -> header + total
//   1 -> winner
//   2..N+1 -> per-candidate breakdown
void renderResultsFrame(int frame) {
  int totalFrames = 2 + resCandCount;
  if (totalFrames < 2) totalFrames = 2;
  int f = ((frame % totalFrames) + totalFrames) % totalFrames;

  if (resTotalVotes == 0) {
    lcdShow("=== RESULTS ===", "No votes yet");
    return;
  }

  if (f == 0) {
    lcdShow("=== RESULTS ===", String("Total votes: ") + resTotalVotes);
  } else if (f == 1) {
    if (resTie) {
      lcdShow("RESULT: TIE", "Top is tied!");
    } else {
      String l2 = resWinner;
      if (resWinnerParty.length() && (l2.length() + resWinnerParty.length() + 3) <= LCD_COLS) {
        l2 = resWinner + " (" + resWinnerParty + ")";
      }
      lcdShow("WINNER:", l2);
    }
  } else {
    int idx = f - 2;
    if (idx < resCandCount) {
      String name = resCandName[idx];
      String votes = String(resCandVotes[idx]);
      int budget = LCD_COLS - (int)votes.length() - 2; // 2 chars for ": "
      if ((int)name.length() > budget && budget > 0) name = name.substring(0, budget);
      lcdShow(String("Cand ") + (idx + 1) + "/" + resCandCount,
              name + ": " + votes);
    }
  }
}

// ---- Event dispatch ------------------------------------------------------
void enterTransient(Screen s = SCR_TRANSIENT) {
  screen = s;
  screenEnterMs = millis();
  screenLastFrameMs = millis();
  screenFrameIdx = 0;
}

void onAdminLogin() {
  renderAdminLogin();
  beep(1, 100, 0);
  ledSet(LED_ON_M);
  enterTransient();
}

void onAdminFaceFail(const String& reason) {
  renderAdminFaceFail(reason);
  beep(3, 120, 100);
  ledSet(LED_BLINK_FAST);
  enterTransient();
}

void onVotingOpen(const String& admin) {
  votingOpen = true;
  renderVotingOpen(admin);
  beep(2, 200, 120);
  ledSet(LED_ON_M);
  enterTransient();
}

void onVotingClosed() {
  votingOpen = false;
  renderVotingClosed();
  beep(1, 400, 0);
  ledSet(LED_ON_M);
  enterTransient();
}

void onVoteClosed() {
  renderVoteClosed();
  beep(2, 100, 100);
  ledSet(LED_BLINK_FAST);
  enterTransient();
}

void onVoterRegistered(int id, const String& name, int total) {
  renderVoterRegistered(id, name, total);
  beep(1, 80, 0);
  ledSet(LED_ON_M);
  enterTransient();
}

void onLoginOk(int id, const String& name) {
  renderLoginOk(id, name);
  beep(1, 120, 80);
  ledSet(LED_ON_M);
  enterTransient();
}

void onLoginFail(const String& reason) {
  renderLoginFail(reason);
  beep(3, 120, 100);
  ledSet(LED_BLINK_FAST);
  enterTransient();
}

void onAlreadyVoted(int id, const String& name) {
  renderAlreadyVoted(id, name);
  beep(2, 100, 100);
  ledSet(LED_BLINK_FAST);
  enterTransient();
}

void onVoteFail(int id, const String& reason) {
  renderVoteFail(id, reason);
  beep(3, 150, 100);
  ledSet(LED_BLINK_FAST);
  enterTransient();
}

void onVoteCast() {
  // payload already cached into vc* fields by handleEvent
  enterTransient(SCR_VOTE_CAST);
  renderVoteCastFrame(0);
  beep(2, 200, 120);
  ledSet(LED_ON_M);
}

void onResults() {
  // payload already cached into res* fields
  screen = SCR_RESULTS;
  screenEnterMs = millis();
  screenLastFrameMs = millis();
  screenFrameIdx = 0;
  renderResultsFrame(0);
  beep(1, 350, 120);
  beep(1, 120, 100);
  beep(1, 350, 0);
  ledSet(LED_PULSE);
}

void onReset() {
  renderResetScreen();
  beep(1, 600, 0);
  ledSet(LED_ON_M);
  totalVotes = 0;
  resCandCount = 0;
  resTotalVotes = 0;
  resWinner = "";
  resWinnerParty = "";
  resTie = false;
  enterTransient();
}

void handleEvent(const String& line) {
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) return;

  const char* event = doc["event"] | "";

  if (strcmp(event, "ADMIN_LOGIN") == 0) {
    onAdminLogin();
  }
  else if (strcmp(event, "ADMIN_FACE_FAIL") == 0) {
    String reason = String((const char*)(doc["reason"] | ""));
    onAdminFaceFail(reason);
  }
  else if (strcmp(event, "VOTING_OPEN") == 0) {
    String admin = String((const char*)(doc["admin"] | ""));
    onVotingOpen(admin);
  }
  else if (strcmp(event, "VOTING_CLOSED") == 0) {
    onVotingClosed();
  }
  else if (strcmp(event, "VOTE_CLOSED") == 0) {
    onVoteClosed();
  }
  else if (strcmp(event, "VOTER_REGISTERED") == 0) {
    int id    = doc["voter_id"] | 0;
    String n  = String((const char*)(doc["name"] | "Voter"));
    int total = doc["total"] | 0;
    onVoterRegistered(id, n, total);
  }
  else if (strcmp(event, "LOGIN_OK") == 0) {
    int id   = doc["voter_id"] | 0;
    String n = String((const char*)(doc["name"] | "Voter"));
    onLoginOk(id, n);
  }
  else if (strcmp(event, "LOGIN_FAIL") == 0) {
    String reason = String((const char*)(doc["reason"] | ""));
    onLoginFail(reason);
  }
  else if (strcmp(event, "ALREADY_VOTED") == 0) {
    int id   = doc["voter_id"] | 0;
    String n = String((const char*)(doc["name"] | "Voter"));
    onAlreadyVoted(id, n);
  }
  else if (strcmp(event, "VOTE_FAIL") == 0) {
    int id        = doc["voter_id"] | 0;
    String reason = String((const char*)(doc["reason"] | ""));
    onVoteFail(id, reason);
  }
  else if (strcmp(event, "VOTE_CAST") == 0) {
    vcVoterId   = doc["voter_id"] | 0;
    vcName      = String((const char*)(doc["name"]      | "Voter"));
    vcCandidate = String((const char*)(doc["candidate"] | "?"));
    vcParty     = String((const char*)(doc["party"]     | "?"));

    int newTotal = 0;
    JsonObject totals = doc["totals"].as<JsonObject>();
    for (JsonPair p : totals) newTotal += p.value().as<int>();
    vcTotalVotes = newTotal;
    totalVotes   = newTotal;

    onVoteCast();
  }
  else if (strcmp(event, "RESULTS") == 0) {
    resTotalVotes  = doc["total_votes"]  | 0;
    resWinner      = String((const char*)(doc["winner"]       | ""));
    resWinnerParty = String((const char*)(doc["winner_party"] | ""));
    resTie         = doc["tie"] | false;

    resCandCount = 0;
    JsonObject cands = doc["candidates"].as<JsonObject>();
    if (!cands.isNull()) {
      for (JsonPair p : cands) {
        if (resCandCount >= MAX_CANDS) break;
        resCandName[resCandCount]  = String(p.key().c_str());
        resCandVotes[resCandCount] = p.value().as<int>();
        resCandCount++;
      }
    } else {
      // fallback: party-level totals
      JsonObject totals = doc["totals"].as<JsonObject>();
      for (JsonPair p : totals) {
        if (resCandCount >= MAX_CANDS) break;
        resCandName[resCandCount]  = String(p.key().c_str());
        resCandVotes[resCandCount] = p.value().as<int>();
        resCandCount++;
      }
    }
    onResults();
  }
  else if (strcmp(event, "RESET") == 0) {
    onReset();
  }
}

// ---- Setup / loop --------------------------------------------------------
void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcdShow("SDV booted", "Waiting host...");
  beep(1, 80, 0);
  ledSet(LED_OFF_M);
  enterTransient();   // show banner then fall to idle
}

void loop() {
  // 1. Pull serial events
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (buf.length() > 0) handleEvent(buf);
      buf = "";
    } else if (c != '\r') {
      buf += c;
      if (buf.length() > 1024) buf = "";
    }
  }

  // 2. LED non-blocking update
  ledTick();

  // 3. Screen state machine
  unsigned long now = millis();

  if (screen == SCR_VOTE_CAST) {
    if (now - screenLastFrameMs > VOTE_FRAME_MS) {
      screenFrameIdx++;
      screenLastFrameMs = now;
      renderVoteCastFrame(screenFrameIdx);
    }
    if (now - screenEnterMs > TRANSIENT_MS) {
      screen = SCR_IDLE;
      ledSet(LED_OFF_M);
      renderIdle();
    }
  }
  else if (screen == SCR_RESULTS) {
    if (now - screenLastFrameMs > RESULTS_FRAME_MS) {
      screenFrameIdx++;
      screenLastFrameMs = now;
      renderResultsFrame(screenFrameIdx);
    }
    if (now - screenEnterMs > RESULTS_DURATION_MS) {
      screen = SCR_IDLE;
      ledSet(LED_OFF_M);
      renderIdle();
    }
  }
  else if (screen == SCR_TRANSIENT) {
    if (now - screenEnterMs > TRANSIENT_MS) {
      screen = SCR_IDLE;
      ledSet(LED_OFF_M);
      renderIdle();
    }
  }
}
