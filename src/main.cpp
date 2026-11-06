#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <M5Dial.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include "map_franca.h"
#include "secrets.h"

namespace {
constexpr char FEED_URL[] = "https://radar.meulab.fun/data/aircraft.json";
constexpr uint32_t FETCH_MS = 15000;
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr size_t MAX_AIRCRAFT = 120;
constexpr uint16_t BG = 0x0864;       // deep navy
constexpr uint16_t PANEL = 0x10E7;
constexpr uint16_t CYAN = 0x36BA;
constexpr uint16_t WHITE = 0xF7BE;
constexpr uint16_t MUTED = 0x9473;
constexpr uint16_t ORANGE = 0xFBA9;
constexpr uint16_t RED = 0xF38B;
constexpr uint16_t GRID = 0x1A6B;
constexpr float MAP_PX_PER_NM = 0.60f;
constexpr float MAP_RANGE_NM = 160.0f;

struct Aircraft {
  String call;
  String reg;
  String type;
  String hex;
  float distance = -1;
  float bearing = -1;
  float speed = -1;
  float track = -1;
  int altitude = -1;
  float seen = 999;
};

Aircraft planes[MAX_AIRCRAFT];
size_t count = 0;
size_t selected = 0;
bool showDetail = false;
bool online = false;
bool feedOK = false;
bool fetching = false;
uint32_t lastFetch = 0;
uint32_t lastSuccess = 0;
uint32_t lastWiFiTry = 0;
uint32_t lastDraw = 0;
uint32_t lastAction = 0;
long lastEncoder = 0;
bool holdTriggered = false;
String errorText;
M5Canvas* canvas = nullptr;
bool spriteOK = false;

String clean(const char* value) {
  String s = value ? value : "";
  s.trim();
  return s;
}

void put(const String& s, int x, int y, int size, uint16_t color, textdatum_t datum = middle_center) {
  auto& d = spriteOK ? static_cast<lgfx::LGFXBase&>(*canvas) : static_cast<lgfx::LGFXBase&>(M5Dial.Display);
  d.setFont(&fonts::Font0);
  d.setTextDatum(datum);
  d.setTextSize(size);
  d.setTextColor(color, BG);
  d.drawString(s, x, y);
}

void putClear(const String& s, int x, int y, uint16_t color) {
  auto& d = spriteOK ? static_cast<lgfx::LGFXBase&>(*canvas) : static_cast<lgfx::LGFXBase&>(M5Dial.Display);
  d.setFont(&fonts::Font0);
  d.setTextDatum(middle_center);
  d.setTextSize(1);
  d.setTextColor(color);
  d.drawString(s, x, y);
}

void planeMarker(lgfx::LGFXBase& d, const Aircraft& p, bool active) {
  if (p.distance < 0 || p.bearing < 0 || p.distance > MAP_RANGE_NM) return;
  float bearing = p.bearing * DEG_TO_RAD;
  int x = 120 + sinf(bearing) * p.distance * MAP_PX_PER_NM;
  int y = 120 - cosf(bearing) * p.distance * MAP_PX_PER_NM;
  float heading = (p.track >= 0 ? p.track : p.bearing) * DEG_TO_RAD;
  float dx = sinf(heading), dy = -cosf(heading);
  float sideX = -dy, sideY = dx;
  int length = active ? 7 : 5;
  uint16_t color = active ? RED : CYAN;
  if (active) d.drawCircle(x, y, 10, RED);
  d.fillTriangle(x + dx * length, y + dy * length,
                 x - dx * length * .6f + sideX * length * .55f,
                 y - dy * length * .6f + sideY * length * .55f,
                 x - dx * length * .6f - sideX * length * .55f,
                 y - dy * length * .6f - sideY * length * .55f, color);
}

void drawRadar(lgfx::LGFXBase& d, bool stale, uint16_t status, uint32_t age) {
  d.fillScreen(BG);
  d.drawPng(MAP_FRANCA_PNG, MAP_FRANCA_PNG_SIZE, 0, 0);
  d.drawCircle(120, 120, 117, status);
  d.drawCircle(120, 120, 96, GRID);
  d.drawCircle(120, 120, 60, GRID);
  d.drawCircle(120, 120, 30, GRID);
  d.drawFastHLine(28, 120, 184, GRID);
  d.drawFastVLine(120, 38, 164, GRID);
  // Subtle moving radar sweep, underneath aircraft markers.
  int sweep = (millis() / 90) % 360;
  for (int offset = 0; offset < 15; offset += 3) {
    float a = (sweep - offset - 90) * DEG_TO_RAD;
    uint16_t shade = offset == 0 ? 0x278E : 0x13EA;
    d.drawLine(120, 120, 120 + cosf(a) * 95, 120 + sinf(a) * 95, shade);
  }
  d.fillCircle(120, 120, 3, WHITE);
  putClear("SIMK", 139, 127, WHITE);
  d.fillCircle(102, 93, 2, MUTED);
  putClear("UBERABA", 83, 85, MUTED);
  d.fillCircle(106, 144, 2, MUTED);
  putClear("RIB. PRETO", 149, 150, MUTED);

  for (size_t i = 0; i < count; ++i) if (i != selected) planeMarker(d, planes[i], false);
  if (count) planeMarker(d, planes[selected], true);

  d.fillRoundRect(43, 15, 154, 37, 9, BG);
  d.drawRoundRect(43, 15, 154, 37, 9, PANEL);
  putClear("MEULAB RADAR  /  SIMK", 120, 27, WHITE);
  d.fillCircle(183, 27, 3, status);
  putClear(String(count) + " VOOS  /  160 NM", 120, 42, CYAN);

  if (!count) {
    String msg = !online ? "SEM WI-FI" : (errorText.length() ? "FALHA FEED" : (!feedOK ? "AGUARDE" : "CEU LIVRE"));
    String sub = !online ? "Reconectando..." : (errorText.length() ? errorText : (!feedOK ? "Buscando aeronaves" : "Nenhum voo no alcance"));
    d.fillRoundRect(36, 88, 168, 48, 10, BG);
    d.drawRoundRect(36, 88, 168, 48, 10, PANEL);
    put(msg, 120, 103, 2, WHITE);
    putClear(sub.substring(0, 24), 120, 124, MUTED);
  } else {
    const Aircraft& p = planes[selected];
    d.fillRoundRect(28, 170, 184, 53, 12, BG);
    d.drawRoundRect(28, 170, 184, 53, 12, CYAN);
    String call = p.call.length() ? p.call : p.hex;
    if (call.length() > 10) call = call.substring(0, 10);
    put(call, 120, 182, 2, RED);
    String meta = (p.type.length() ? p.type : "--") + String("  /  ") +
      (p.distance >= 0 ? String(p.distance, 1) : String("--")) + " NM";
    put(meta, 120, 198, 1, WHITE);
    String values = (p.altitude >= 0 ? String(p.altitude) : String("--")) + " FT    " +
      (p.speed >= 0 ? String(p.speed, 0) : String("--")) + " KT";
    put(values, 120, 211, 1, MUTED);
  }
  if (stale) {
    String state = !online ? "SEM WI-FI" : "DADOS ANTIGOS";
    if (lastSuccess) state += " " + String(age) + "s";
    d.fillRoundRect(56, 225, 128, 13, 5, BG);
    putClear(state, 120, 231, status);
  }
}

void draw() {
  auto& d = spriteOK ? static_cast<lgfx::LGFXBase&>(*canvas) : static_cast<lgfx::LGFXBase&>(M5Dial.Display);
  d.fillScreen(BG);
  uint32_t age = lastSuccess ? (millis() - lastSuccess) / 1000 : 0;
  bool stale = !feedOK || !lastSuccess || age > 45;
  uint16_t status = !online ? RED : (stale ? ORANGE : CYAN);
  if (!showDetail) {
    drawRadar(d, stale, status, age);
    if (spriteOK) canvas->pushSprite(0, 0);
    lastDraw = millis();
    return;
  }
  d.drawCircle(120, 120, 117, status);
  d.drawCircle(120, 120, 116, PANEL);
  for (int deg = 0; deg < 360; deg += 15) {
    float a = (deg - 90) * DEG_TO_RAD;
    int inner = deg % 90 == 0 ? 106 : 110;
    d.drawLine(120 + cosf(a) * inner, 120 + sinf(a) * inner,
               120 + cosf(a) * 113, 120 + sinf(a) * 113,
               deg % 90 == 0 ? MUTED : PANEL);
  }

  if (count && planes[selected].bearing >= 0) {
    float a = (planes[selected].bearing - 90.0f) * DEG_TO_RAD;
    int px = 120 + cosf(a) * 113;
    int py = 120 + sinf(a) * 113;
    d.fillCircle(px, py, 4, CYAN);
  }

  put("MEULAB  /  RADAR", 120, 32, 1, CYAN);
  if (!online && count == 0) {
    put("SEM WI-FI", 120, 99, 2, WHITE);
    put("Reconectando...", 120, 135, 1, MUTED);
    put("Verifique sua rede", 120, 160, 1, CYAN);
  } else if (!feedOK && count == 0) {
    put("SEM DADOS", 120, 99, 2, WHITE);
    put(errorText.substring(0, 24), 120, 135, 1, MUTED);
    put("Aguarde atualizacao", 120, 160, 1, CYAN);
  } else if (count == 0) {
    put("CEU LIMPO", 120, 100, 2, WHITE);
    put("Nenhum voo no alcance", 120, 137, 1, MUTED);
  } else {
    const auto& p = planes[selected];
    put(String(selected + 1) + " / " + String(count) + " AERONAVES", 120, 54, 1, MUTED);
    String call = p.call.length() ? p.call : p.hex;
    if (call.length() > 10) call = call.substring(0, 10);
    d.setFont(&fonts::Orbitron_Light_32);
    d.setTextDatum(middle_center);
    d.setTextSize(1);
    d.setTextColor(WHITE, BG);
    if (d.textWidth(call) > 202) d.setFont(&fonts::Font0);
    if (d.textWidth(call) > 202) d.setTextSize(2);
    d.drawString(call, 120, 89);
    d.setFont(&fonts::Font0);
    String identity = p.reg;
    if (p.type.length()) identity += (identity.length() ? "  /  " : "") + p.type;
    if (!identity.length()) identity = p.hex;
    put(identity.substring(0, 22), 120, 116, 1, MUTED);

    if (!showDetail) {
      String dist = p.distance >= 0 ? String(p.distance, p.distance < 100 ? 1 : 0) + " NM" : "-- NM";
      put(dist, 120, 151, 2, CYAN);
      d.fillRoundRect(40, 174, 76, 29, 10, PANEL);
      d.fillRoundRect(124, 174, 76, 29, 10, PANEL);
      put(p.altitude >= 0 ? String(p.altitude) + " ft" : "-- ft", 78, 188, 1, WHITE);
      put(p.speed >= 0 ? String(p.speed, 0) + " kt" : "-- kt", 162, 188, 1, WHITE);
      String footer = !online ? "SEM WI-FI" : (stale ? "DADOS ANTIGOS" : "GIRE: VOO   TOQUE: DETALHE");
      if (stale && lastSuccess) footer += "  " + String(age) + "s";
      put(footer, 120, 218, 1, stale ? ORANGE : MUTED);
    } else {
      d.drawFastHLine(48, 136, 144, PANEL);
      put("ALTITUDE", 75, 153, 1, MUTED);
      put("VELOCIDADE", 165, 153, 1, MUTED);
      put(p.altitude >= 0 ? String(p.altitude) + " ft" : "--", 75, 172, 1, WHITE);
      put(p.speed >= 0 ? String(p.speed, 0) + " kt" : "--", 165, 172, 1, WHITE);
      String route = "RUMO " + (p.track >= 0 ? String(p.track, 0) : String("--")) + "°";
      route += "  /  " + (p.distance >= 0 ? String(p.distance, 1) : String("--")) + " NM";
      put(route, 120, 195, 1, CYAN);
      String footer = !online ? "SEM WI-FI" : (stale ? "DADOS ANTIGOS" : "TOQUE: VOLTAR");
      if (stale && lastSuccess) footer += "  " + String(age) + "s";
      put(footer, 120, 218, 1, stale ? ORANGE : MUTED);
    }
  }
  if (spriteOK) canvas->pushSprite(0, 0);
  lastDraw = millis();
}

void beginWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiTry = millis();
  Serial.println("Wi-Fi connecting");
}

void fetchFeed() {
  if (WiFi.status() != WL_CONNECTED) return;
  fetching = true;
  lastFetch = millis();
  WiFiClientSecure client;
  client.setInsecure(); // Public, read-only feed; no credentials sent to server.
  client.setTimeout(8000);
  HTTPClient http;
  http.useHTTP10(true);
  http.setTimeout(8000);
  if (!http.begin(client, FEED_URL)) {
    errorText = "URL indisponivel";
    feedOK = false;
    fetching = false;
    return;
  }
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    errorText = "HTTP " + String(code);
    feedOK = false;
    http.end();
    fetching = false;
    return;
  }

  JsonDocument filter;
  JsonObject aircraftFilter = filter["aircraft"].add<JsonObject>();
  aircraftFilter["flight"] = true;
  aircraftFilter["r"] = true;
  aircraftFilter["t"] = true;
  aircraftFilter["hex"] = true;
  aircraftFilter["r_dst"] = true;
  aircraftFilter["r_dir"] = true;
  aircraftFilter["alt_baro"] = true;
  aircraftFilter["gs"] = true;
  aircraftFilter["track"] = true;
  aircraftFilter["seen"] = true;
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();
  if (err) {
    errorText = "JSON invalido";
    feedOK = false;
    fetching = false;
    Serial.println(err.c_str());
    return;
  }

  String keepHex = selected < count ? planes[selected].hex : "";
  count = 0;
  for (JsonObject obj : doc["aircraft"].as<JsonArray>()) {
    if (count >= MAX_AIRCRAFT) break;
    float seen = obj["seen"] | 999.0f;
    if (seen > 60) continue;
    Aircraft p;
    p.call = clean(obj["flight"] | "");
    p.reg = clean(obj["r"] | "");
    p.type = clean(obj["t"] | "");
    p.hex = clean(obj["hex"] | "");
    p.distance = obj["r_dst"] | -1.0f;
    p.bearing = obj["r_dir"] | -1.0f;
    p.speed = obj["gs"] | -1.0f;
    p.track = obj["track"] | -1.0f;
    p.altitude = obj["alt_baro"].is<int>() ? obj["alt_baro"].as<int>() : -1;
    p.seen = seen;
    planes[count++] = p;
  }
  // Nearest aircraft first; unknown distances last.
  for (size_t i = 1; i < count; ++i) {
    Aircraft p = planes[i];
    size_t j = i;
    while (j && (planes[j - 1].distance < 0 ||
           (p.distance >= 0 && planes[j - 1].distance > p.distance))) {
      planes[j] = planes[j - 1];
      --j;
    }
    planes[j] = p;
  }
  selected = 0;
  for (size_t i = 0; i < count; ++i) if (planes[i].hex == keepHex && keepHex.length()) { selected = i; break; }
  feedOK = true;
  lastSuccess = millis();
  errorText = "";
  fetching = false;
  Serial.printf("Feed OK: %u aircraft\n", static_cast<unsigned>(count));
  draw();
}
} // namespace

void setup() {
  Serial.begin(115200);
  auto cfg = M5.config();
  M5Dial.begin(cfg, true, false);
  M5Dial.Display.setBrightness(130);
  canvas = new M5Canvas(&M5Dial.Display);
  canvas->setColorDepth(16);
  spriteOK = canvas->createSprite(240, 240) != nullptr;
  draw();
  beginWiFi();
  lastEncoder = M5Dial.Encoder.read();
}

void loop() {
  M5Dial.update();
  bool nowOnline = WiFi.status() == WL_CONNECTED;
  if (nowOnline != online) {
    online = nowOnline;
    if (!online) feedOK = false;
    draw();
  }
  if (!online && millis() - lastWiFiTry > WIFI_RETRY_MS) beginWiFi();

  long encoder = M5Dial.Encoder.read();
  long steps = (encoder - lastEncoder) / 4;
  if (steps && count) {
    long next = (static_cast<long>(selected) + steps) % static_cast<long>(count);
    if (next < 0) next += count;
    selected = static_cast<size_t>(next);
    lastEncoder += steps * 4;
    draw();
  } else if (!count) lastEncoder = encoder;
  if (M5Dial.BtnA.wasReleased()) holdTriggered = false;
  if (!holdTriggered && M5Dial.BtnA.pressedFor(1200)) {
    holdTriggered = true;
    lastFetch = 0;
  }
  if (millis() - lastAction > 250) {
    bool tapped = M5Dial.Touch.getDetail().wasClicked();
    if (M5Dial.BtnA.wasPressed() || tapped) {
      showDetail = !showDetail;
      lastAction = millis();
      draw();
    }
  }
  if (online && !fetching && (lastFetch == 0 || millis() - lastFetch >= FETCH_MS)) fetchFeed();
  if (millis() - lastDraw > 1000) draw();
  delay(8);
}
