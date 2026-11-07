// Interactive simulator: runs the real firmware setup()/loop() (../src/main.cpp)
// in an SDL window with live input.
// Usage: program [feed.json] [--quit-after SECONDS] [--shot out.png]
//   click         = touch tap          Left/Right, wheel = encoder (1 detent)
//   Space         = button A (hold >1.2 s = refresh; hold + arrows works)
//   W             = toggle Wi-Fi       F = toggle HTTP 503     Esc/Q = quit
#include <atomic>
#include <chrono>
#include <fstream>
#include <sstream>
#include <thread>
#include <ctime>

#include "main.cpp"

uint32_t sim_millis = 0;
int sim_hour = -1;  // updated from the host clock (as if NTP synced)
SerialShim Serial;
EspShim ESP;
WiFiShim WiFi;
SimM5 M5;
SimDial M5Dial;
int sim_http_code = 200;
std::string sim_http_body;

namespace sim {
constexpr uint32_t FETCH_LATENCY_MS = 400;  // fake network time, makes "refreshing" visible

M5GFX lcd;  // SDL window (board/scale/frame chosen by build flags)
M5Canvas frame(&lcd);

std::atomic<bool> btnDown{false};
std::atomic<long> encoderCounts{0};
std::atomic<bool> toggleWiFi{false}, toggleHttp{false};
std::string shotPath;
double quitAfter = 0;

void quit() {
  SDL_Event e{};
  e.type = SDL_QUIT;
  SDL_PushEvent(&e);
}

// Runs on the SDL (main) thread while Panel_sdl polls events; only touches atomics.
int eventWatch(void*, SDL_Event* e) {
  if (e->type == SDL_KEYDOWN || e->type == SDL_KEYUP) {
    bool down = e->type == SDL_KEYDOWN;
    switch (e->key.keysym.sym) {
      case SDLK_SPACE: btnDown = down; break;
      case SDLK_RIGHT: if (down) encoderCounts += 4; break;  // key repeat = more detents
      case SDLK_LEFT: if (down) encoderCounts -= 4; break;
      case SDLK_w: if (down && !e->key.repeat) toggleWiFi = true; break;
      case SDLK_f: if (down && !e->key.repeat) toggleHttp = true; break;
      case SDLK_ESCAPE:
      case SDLK_q: if (down) quit(); break;
      default: break;
    }
  } else if (e->type == SDL_MOUSEWHEEL) {
    int y = e->wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -e->wheel.y : e->wheel.y;
    encoderCounts += 4L * y;
  }
  return 0;
}

uint32_t realMillis() {
  static const auto t0 = std::chrono::steady_clock::now();
  return 1000 + static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                                          std::chrono::steady_clock::now() - t0).count());
}

void applyInput() {
  M5Dial.BtnA.raw = btnDown;
  M5Dial.Encoder.value += encoderCounts.exchange(0);
  lgfx::touch_point_t tp;
  bool touched = lcd.getTouch(&tp) > 0;
  M5Dial.Touch.raw = touched;
  if (touched) { M5Dial.Touch.x = tp.x; M5Dial.Touch.y = tp.y; }
  if (toggleWiFi.exchange(false)) {
    WiFi.state = WiFi.state == WL_CONNECTED ? WL_DISCONNECTED : WL_CONNECTED;
    std::printf("[sim] Wi-Fi %s\n", WiFi.state == WL_CONNECTED ? "connected" : "disconnected");
  }
  if (toggleHttp.exchange(false)) {
    sim_http_code = sim_http_code == 200 ? 503 : 200;
    std::printf("[sim] HTTP %d\n", sim_http_code);
  }
}

// Stand-in for fetchTask (the shim never starts FreeRTOS tasks).
void serviceFetch() {
  static uint32_t started = 0;
  if (!fetching) { started = 0; return; }
  if (!started) started = millis();
  if (millis() - started < FETCH_LATENCY_MS) return;
  fetchOnce();
  fetching = false;
  started = 0;
}

void present() {
  M5Dial.Display.pushSprite(&frame, 0, 0);
  frame.fillArc(120, 120, 170, 120, 0, 360, TFT_BLACK);  // round panel mask
  frame.pushSprite(0, 0);
}

int run(bool* running) {
  lcd.init();
  frame.setColorDepth(16);
  frame.createSprite(240, 240);
  SDL_AddEventWatch(eventWatch, nullptr);

  sim_millis = realMillis();
  setup();
  uint32_t lastPresent = 0;
  while (*running) {
    sim_millis = std::max(sim_millis, realMillis());  // firmware delay() also advances it
    std::time_t t = std::time(nullptr);
    sim_hour = std::localtime(&t)->tm_hour;
    applyInput();
    serviceFetch();
    loop();
    if (millis() - lastPresent >= 16) {
      present();
      lastPresent = millis();
    }
    if (quitAfter > 0 && realMillis() - 1000 >= quitAfter * 1000) {
      quitAfter = 0;
      quit();
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(8));  // matches firmware delay(8)
  }
  if (!shotPath.empty()) {
    present();
    size_t len = 0;
    void* png = frame.createPng(&len, 0, 0, 240, 240);
    if (png) {
      std::ofstream(shotPath, std::ios::binary).write(static_cast<const char*>(png), len);
      free(png);
      std::printf("[sim] wrote %s\n", shotPath.c_str());
    }
  }
  return 0;
}
}  // namespace sim

int main(int argc, char** argv) {
  std::string feedPath = "fixtures/aircraft.json";
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--quit-after" && i + 1 < argc) sim::quitAfter = std::atof(argv[++i]);
    else if (a == "--shot" && i + 1 < argc) sim::shotPath = argv[++i];
    else if (a == "-h" || a == "--help") {
      std::printf("usage: %s [feed.json] [--quit-after SECONDS] [--shot out.png]\n", argv[0]);
      return 0;
    } else feedPath = a;
  }
  std::ifstream in(feedPath);
  if (!in) {
    std::fprintf(stderr, "cannot read %s\n", feedPath.c_str());
    return 1;
  }
  std::stringstream ss;
  ss << in.rdbuf();
  sim_http_body = ss.str();
  std::printf("[sim] feed %s (%zu bytes). Click=tap, arrows/wheel=encoder, Space=button, "
              "W=Wi-Fi, F=HTTP 503, Esc=quit\n", feedPath.c_str(), sim_http_body.size());
  std::fflush(stdout);
  return lgfx::Panel_sdl::main(sim::run, 128);
}
