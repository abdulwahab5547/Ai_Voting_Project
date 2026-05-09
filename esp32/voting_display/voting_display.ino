/*
 * Smart Digital Voting Machine — ESP32 Booth Display
 *
 * Hardware
 *   ESP32 dev board
 *   0.96" OLED SSD1306 (I2C) on SDA = GPIO 21, SCL = GPIO 22
 *   Passive buzzer on GPIO 25
 *
 * Required libraries (Library Manager):
 *   Adafruit SSD1306
 *   Adafruit GFX Library
 *   ArduinoJson  (v6.x)
 *
 * Serial protocol:
 *   The Flask app sends newline-delimited JSON, e.g.
 *     {"event":"LOGIN_OK","name":"John"}
 *     {"event":"LOGIN_FAIL"}
 *     {"event":"ALREADY_VOTED","name":"John"}
 *     {"event":"VOTE_CAST","name":"John","candidate":"X","party":"PTI",
 *       "totals":{"PTI":47,"PMLN":33}}
 *     {"event":"VOTER_REGISTERED","name":"John","total":12}
 *     {"event":"RESULTS","totals":{"PTI":47,"PMLN":33},"total_votes":80,
 *       "winner":"PTI","tie":false}
 *     {"event":"RESET"}
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

#define SCREEN_W 128
#define SCREEN_H 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C
#define BUZZER_PIN 25

Adafruit_SSD1306 display(SCREEN_W, SCREEN_H, &Wire, OLED_RESET);

unsigned long lastEventMs = 0;
unsigned long resultsEnterMs = 0;
const unsigned long TRANSIENT_MS = 3500;     // how long a flash screen lingers
const unsigned long RESULTS_DURATION_MS = 12000; // how long the RESULTS screen sticks

int    totalVotes = 0;
int    totalVoters = 0;            // updated by VOTER_REGISTERED
String topParty   = "";
int    topCount   = 0;
String partySummary;                // "PTI:12 PMLN:8 PPP:4"

// Cached results payload so we can re-render / scroll the RESULTS screen.
const int  MAX_PARTIES = 8;
String     resPartyName[MAX_PARTIES];
int        resPartyVotes[MAX_PARTIES];
int        resPartyCount = 0;
int        resTotalVotes = 0;
String     resWinner = "";
bool       resTie = false;
bool       resultsActive = false;
int        resultsScrollIdx = 0;
unsigned long resultsLastScrollMs = 0;
const unsigned long RESULTS_SCROLL_MS = 1800;

void beep(int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    tone(BUZZER_PIN, 2000);
    delay(onMs);
    noTone(BUZZER_PIN);
    delay(offMs);
  }
}

void drawHeader(const char* title) {
  display.clearDisplay();
  display.fillRect(0, 0, SCREEN_W, 12, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setTextSize(1);
  display.setCursor(2, 2);
  display.print(title);
  display.setTextColor(SSD1306_WHITE);
}

void showSummary() {
  drawHeader(" SDV  STATUS");
  display.setCursor(0, 18);
  display.setTextSize(1);
  display.print("Total votes: ");
  display.println(totalVotes);

  display.setCursor(0, 32);
  if (totalVotes > 0 && topParty.length() > 0) {
    display.print("Leading: ");
    display.println(topParty);
    display.setCursor(0, 44);
    display.print("Top count: ");
    display.println(topCount);
  } else {
    display.println("Waiting for events...");
  }

  display.setCursor(0, 56);
  display.setTextSize(1);
  display.print(partySummary.length() ? partySummary : String("Ready."));
  display.display();
}

void showLoginOk(const String& name) {
  drawHeader(" LOGIN OK");
  display.setTextSize(1);
  display.setCursor(0, 22);
  display.print("Welcome,");
  display.setTextSize(2);
  display.setCursor(0, 36);
  display.print(name.length() > 10 ? name.substring(0, 10) : name);
  display.display();
  beep(1, 120, 80);
}

void showLoginFail() {
  drawHeader(" ACCESS DENIED");
  display.setTextSize(2);
  display.setCursor(0, 24);
  display.print("NOT");
  display.setCursor(0, 44);
  display.print("REGISTERED");
  display.display();
  beep(3, 120, 100);
}

void showAlreadyVoted(const String& name) {
  drawHeader(" ALREADY VOTED");
  display.setTextSize(1);
  display.setCursor(0, 24);
  display.print(name);
  display.setCursor(0, 40);
  display.print("Already cast vote.");
  display.display();
  beep(2, 100, 100);
}

void showVoteCast(const String& name, const String& party, int total, const String& summary) {
  drawHeader(" VOTE ACCEPTED");
  display.setTextSize(1);
  display.setCursor(0, 16);
  display.print("Voter: "); display.println(name);
  display.setCursor(0, 28);
  display.print("Party: "); display.println(party);
  display.setCursor(0, 40);
  display.print("Total: "); display.println(total);
  display.setCursor(0, 54);
  display.print(summary);
  display.display();
  beep(2, 200, 120);
}

void showReset() {
  drawHeader(" ELECTION RESET");
  display.setTextSize(1);
  display.setCursor(0, 28);
  display.println("Votes cleared.");
  display.println("Voters retained.");
  display.display();
  beep(1, 600, 0);
  totalVotes = 0;
  topParty = "";
  topCount = 0;
  partySummary = "";
  resultsActive = false;
}

void showVoterRegistered(const String& name, int total) {
  drawHeader(" VOTER REGISTERED");
  display.setTextSize(1);
  display.setCursor(0, 18);
  display.print("Name: ");
  display.println(name.length() > 16 ? name.substring(0, 16) : name);
  display.setCursor(0, 32);
  display.print("Total voters: ");
  display.println(total);
  display.setCursor(0, 50);
  display.print("Database updated.");
  display.display();
  beep(1, 80, 0);
}

void renderResults() {
  drawHeader(" ELECTION RESULTS");

  display.setTextSize(1);
  if (resTotalVotes == 0) {
    display.setCursor(0, 22);
    display.println("No votes yet.");
    display.setCursor(0, 36);
    display.print("Voters: ");
    display.println(totalVoters);
    display.display();
    return;
  }

  // Winner banner
  display.setCursor(0, 16);
  if (resTie) {
    display.print("TIE at top!");
  } else {
    display.print("WINNER:");
  }
  display.setTextSize(2);
  display.setCursor(0, 26);
  String w = resTie ? String("TIE") : (resWinner.length() ? resWinner : String("-"));
  if (w.length() > 9) w = w.substring(0, 9);
  display.print(w);

  // Scrolling per-party list (2 rows visible at the bottom)
  display.setTextSize(1);
  int visible = 2;
  int startIdx = (resPartyCount <= visible) ? 0 : resultsScrollIdx;
  for (int row = 0; row < visible; row++) {
    int idx = (startIdx + row) % (resPartyCount > 0 ? resPartyCount : 1);
    if (idx >= resPartyCount) break;
    int y = 48 + row * 8;
    display.setCursor(0, y);
    String label = resPartyName[idx];
    if (label.length() > 10) label = label.substring(0, 10);
    int pct = (resTotalVotes > 0) ? (resPartyVotes[idx] * 100 / resTotalVotes) : 0;
    display.print(label);
    display.print(": ");
    display.print(resPartyVotes[idx]);
    display.print(" (");
    display.print(pct);
    display.print("%)");
  }
  display.display();
}

void showResults() {
  resultsActive = true;
  resultsEnterMs = millis();
  resultsScrollIdx = 0;
  resultsLastScrollMs = millis();
  renderResults();
  // Buzzer pattern: long-short-long  (election-style fanfare)
  beep(1, 350, 120);
  beep(1, 120, 100);
  beep(1, 350, 0);
}

void handleEvent(const String& line) {
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) return;

  const char* event = doc["event"] | "";
  if (strcmp(event, "LOGIN_OK") == 0) {
    showLoginOk(String((const char*)(doc["name"] | "Voter")));
  } else if (strcmp(event, "LOGIN_FAIL") == 0) {
    showLoginFail();
  } else if (strcmp(event, "ALREADY_VOTED") == 0) {
    showAlreadyVoted(String((const char*)(doc["name"] | "Voter")));
  } else if (strcmp(event, "VOTE_CAST") == 0) {
    String name  = String((const char*)(doc["name"]  | "Voter"));
    String party = String((const char*)(doc["party"] | "?"));

    int newTotal = 0;
    String summary = "";
    JsonObject totals = doc["totals"].as<JsonObject>();
    String localTopParty = "";
    int    localTopCount = -1;
    for (JsonPair p : totals) {
      int v = p.value().as<int>();
      newTotal += v;
      if (summary.length() < 20) {
        if (summary.length() > 0) summary += " ";
        summary += String(p.key().c_str()) + ":" + String(v);
      }
      if (v > localTopCount) { localTopCount = v; localTopParty = String(p.key().c_str()); }
    }
    totalVotes = newTotal;
    topParty   = localTopParty;
    topCount   = localTopCount;
    partySummary = summary;

    showVoteCast(name, party, totalVotes, summary);
  } else if (strcmp(event, "VOTER_REGISTERED") == 0) {
    String name = String((const char*)(doc["name"] | "Voter"));
    int total = doc["total"] | 0;
    totalVoters = total;
    showVoterRegistered(name, total);
  } else if (strcmp(event, "RESULTS") == 0) {
    resTotalVotes = doc["total_votes"] | 0;
    resWinner = String((const char*)(doc["winner"] | ""));
    resTie    = doc["tie"] | false;

    resPartyCount = 0;
    JsonObject totals = doc["totals"].as<JsonObject>();
    for (JsonPair p : totals) {
      if (resPartyCount >= MAX_PARTIES) break;
      resPartyName[resPartyCount]  = String(p.key().c_str());
      resPartyVotes[resPartyCount] = p.value().as<int>();
      resPartyCount++;
    }
    showResults();
    return; // results handles its own timing
  } else if (strcmp(event, "RESET") == 0) {
    showReset();
  }
  lastEventMs = millis();
}

void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.begin(115200);
  Wire.begin(21, 22);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    while (true) { delay(1000); }
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(" SDV booted.");
  display.println(" Waiting for host...");
  display.display();
  beep(1, 80, 0);
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (buf.length() > 0) handleEvent(buf);
      buf = "";
    } else if (c != '\r') {
      buf += c;
      if (buf.length() > 1024) buf = "";  // overflow guard
    }
  }

  // RESULTS screen: scroll the per-party list while it's active, then exit.
  if (resultsActive) {
    if (resPartyCount > 2 && millis() - resultsLastScrollMs > RESULTS_SCROLL_MS) {
      resultsScrollIdx = (resultsScrollIdx + 1) % resPartyCount;
      resultsLastScrollMs = millis();
      renderResults();
    }
    if (millis() - resultsEnterMs > RESULTS_DURATION_MS) {
      resultsActive = false;
      lastEventMs = millis();   // fall back to summary via the normal path
    }
    return;
  }

  if (lastEventMs && millis() - lastEventMs > TRANSIENT_MS) {
    showSummary();
    lastEventMs = 0;
  }
}
