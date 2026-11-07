// Desktop simulator: runs the real firmware UI (../src/main.cpp) against a saved
// aircraft.json and writes one PNG per UI state.
// Usage: program <aircraft.json> <out_dir>
#include <sys/stat.h>
#include <fstream>
#include <sstream>
#include <vector>

#include "main.cpp"

uint32_t sim_millis = 0;
int sim_hour = -1;
SerialShim Serial;
EspShim ESP;
WiFiShim WiFi;
SimM5 M5;
SimDial M5Dial;
int sim_http_code = 200;
std::string sim_http_body;

static std::string outDir;

static void snapshot(const char* name) {
  draw();
  size_t len = 0;
  void* png = M5Dial.Display.createPng(&len, 0, 0, 240, 240);
  std::string path = outDir + "/" + name + ".png";
  std::ofstream(path, std::ios::binary).write(static_cast<const char*>(png), len);
  free(png);
  std::printf("wrote %s\n", path.c_str());
}

static void feed(const std::string& json, int code = 200) {
  sim_http_body = json;
  sim_http_code = code;
  fetchOnce();
  applyFetchResult();
}

// Panels visible (recent input), no banners.
static void active() {
  lastInput = sim_millis;
  bannerUntil = 0;
  alertUntil = 0;
}

static void resetState() {
  screen = Screen::Radar;
  muted = false;
  if (sortMode != Sort::Near) setSort(-static_cast<int>(sortMode));
  otaPct = -1;
  refreshing = false;
  online = true;
  zoom = 0;
  WiFi.state = WL_CONNECTED;
  active();
}

static void selectHex(const char* hex) {
  for (size_t i = 0; i < count; ++i) if (!strcmp(planes[i].hex, hex)) { selected = i; return; }
}

// Synthetic aircraft JSON helper.
static std::string ac(const char* hex, const char* flight, const char* r, const char* t, float dst, float dir,
                      const char* alt, float gs, float track, const char* extra = "") {
  char b[512];
  snprintf(b, sizeof b,
           R"({"hex":"%s","flight":"%s","r":"%s","t":"%s","r_dst":%.1f,"r_dir":%.1f,"alt_baro":%s,"gs":%.0f,"track":%.0f,"seen":1%s})",
           hex, flight, r, t, dst, dir, alt, gs, track, extra);
  return b;
}

static std::string feedOf(const std::vector<std::string>& list) {
  std::string s = R"({"aircraft":[)";
  for (size_t i = 0; i < list.size(); ++i) s += (i ? "," : "") + list[i];
  return s + "]}";
}

int main(int argc, char** argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: %s aircraft.json out_dir\n", argv[0]);
    return 1;
  }
  std::stringstream ss;
  ss << std::ifstream(argv[1]).rdbuf();
  const std::string live = ss.str();
  outDir = argv[2];
  mkdir(outDir.c_str(), 0755);

  sim_millis = 1000;
  setup();
  online = true;
  active();
  snapshot("01_boot_aguarde");

  // ---- Live feed ----
  sim_millis = 10000;
  feed(live);
  sim_millis = 12000;
  active();
  snapshot("02_radar_160");
  sim_millis = 12000 + PANEL_HIDE_MS + 1500;  // idle -> panels hide
  snapshot("03_radar_hidden");
  active();
  zoom = 1;
  snapshot("04_zoom_80");
  zoom = 2;
  snapshot("05_zoom_40");
  zoom = 3;
  snapshot("06_zoom_20");
  setZoom(-1);
  snapshot("07_zoom_banner");
  resetState();
  screen = Screen::Detail;
  snapshot("08_detail");
  resetState();

  // Selected in the south half -> card moves to the top.
  for (size_t i = 0; i < count; ++i)
    if (inRange(planes[i]) && planes[i].bearing > 150 && planes[i].bearing < 210 && planes[i].distance > 60) {
      selected = i;
      break;
    }
  snapshot("09_selected_south");
  // Selected beyond range -> edge arrow.
  for (size_t i = 0; i < count; ++i) if (planes[i].distance > RANGES[0]) { selected = i; break; }
  snapshot("10_selected_far");
  selected = 0;

  refreshing = true;
  snapshot("11_refreshing");
  refreshing = false;
  sim_millis = lastSuccess + 76000;
  active();
  snapshot("12_stale_76s");
  screen = Screen::Detail;
  snapshot("13_detail_stale");
  resetState();
  online = false;
  snapshot("14_offline_with_data");
  resetState();

  // ---- Synthetic: field edge cases + trails + alerts ----
  sim_millis = 400000;
  count = 0;  // fresh start (no trails, no approach alert on first feed)
  auto step = [&](int k) {
    // GLO moves inbound towards home; AZU climbs out; hex-only stays.
    return feedOf({
        ac("E48AC0", "GLO1234 ", "PR-GXZ", "B38M", 20.0f - k * 3.0f, 300, "9000", 250, 120, R"(,"baro_rate":-1100,"desc":"BOEING 737 MAX 8","squawk":"4521")"),
        ac("E49001", "AZU4510 ", "PR-AUQ", "A20N", 14.0f + k * 2.5f, 60 + k * 2, "14000", 330, 60, R"(,"baro_rate":2200,"desc":"AIRBUS A320NEO","squawk":"1342")"),
        R"({"hex":"e4a1b2","r_dst":17.0,"r_dir":220,"seen":1})",
        ac("E48F00", "PTB2201 ", "PP-PTB", "AT76", 3.2f, 160, R"("ground")", 12, 90, R"(,"desc":"ATR 72-600")"),
        ac("E49999", "WIDEBODYX", "PP-ABCDEFG", "A35K", 150.0f, 200, "41000", 512, 15, R"(,"desc":"AIRBUS A350-1000 XWB LONG NAME")"),
    });
  };
  for (int k = 0; k < 4; ++k) {
    sim_millis += 15000;
    feed(step(k));
  }
  resetState();
  zoom = 2;  // 40 NM: trails visible
  selectHex("E48AC0");
  snapshot("15_trails_40nm");
  bannerUntil = sim_millis + ALERT_MS;  // keep whatever banner fired (approach)
  sim_millis += 15000;
  feed(step(4));  // GLO crosses 10 NM -> approach alert
  snapshot("16_approach_alert");
  resetState();
  zoom = 2;
  selectHex("E4A1B2");
  snapshot("17_hex_only");
  screen = Screen::Detail;
  snapshot("18_detail_hex_only");
  selectHex("E48F00");
  snapshot("19_detail_ground");
  selectHex("E49001");
  snapshot("20_detail_climb");
  selectHex("E49999");
  snapshot("21_detail_long_ids");
  resetState();

  // Emergency squawk appears -> auto-select, banner, flashing.
  sim_millis += 15000;
  {
    std::string f = step(5);
    f.insert(f.size() - 2, "," + ac("E4E770", "ONE6701 ", "PS-ONE", "A320", 35, 100, "21000", 380, 280,
                                    R"(,"squawk":"7700","emergency":"general","desc":"AIRBUS A320")"));
    feed(f);
  }
  zoom = 1;
  lastInput = sim_millis;
  snapshot("22_emergency");
  screen = Screen::Detail;
  snapshot("23_detail_emergency");
  resetState();

  // ---- Empty / error states ----
  feed(R"({"aircraft":[]})");
  snapshot("24_empty_sky");
  count = 0;
  lastSuccess = 0;
  feed("", 503);
  snapshot("25_http_error_empty");
  online = false;
  WiFi.state = WL_DISCONNECTED;
  snapshot("26_no_wifi_empty");
  screen = Screen::Detail;
  snapshot("27_detail_no_wifi");
  screen = Screen::Radar;
  startPortal();
  snapshot("28_wifi_portal");
  screen = Screen::Detail;
  snapshot("29_detail_portal");

  // ---- Military, sort, stats, mute, clock, OTA ----
  delete portal;
  portal = nullptr;
  resetState();
  errorText = "";
  sim_millis += 15000;
  const std::string base = step(5);
  feed(base);
  std::string withMil = base;
  withMil.insert(withMil.size() - 2, "," + ac("E49F00", "FAB2105 ", "FAB2105", "E390", 25, 330, "18000", 300, 140,
                                             R"(,"dbFlags":1,"desc":"EMBRAER KC-390","squawk":"2000")"));
  sim_millis += 15000;
  feed(withMil);  // new military aircraft -> gold marker + alert
  zoom = 2;
  lastInput = sim_millis;
  snapshot("30_military_alert");
  selectHex("E49F00");
  screen = Screen::Detail;
  snapshot("31_detail_military");
  setSort(1);  // hold+turn on detail -> sort by altitude
  snapshot("32_detail_sort_alt");
  resetState();
  screen = Screen::Stats;
  timeConfigured = true;
  sim_hour = 9;
  snapshot("33_stats");
  timeConfigured = false;
  sim_hour = -1;
  resetState();
  muted = true;
  snapshot("34_muted_header");
  resetState();

  timeConfigured = true;
  sim_hour = 14;
  feed(R"({"aircraft":[]})");
  sim_millis += CLOCK_IDLE_MS + 1000;  // idle + empty sky -> clock
  bannerUntil = 0;
  snapshot("35_clock_empty");
  feed(withMil);
  sim_hour = 23;  // night + idle -> clock even with traffic
  bannerUntil = 0;
  snapshot("36_clock_night");
  sim_hour = -1;
  timeConfigured = false;
  active();
  otaPct = 63;
  snapshot("37_ota_progress");
  otaPct = -1;
  return 0;
}
