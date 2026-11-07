// Minimal Arduino API for the desktop simulator.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#define PROGMEM
#include <cstdlib>
#include <ctime>
#ifndef RAD_TO_DEG
#define RAD_TO_DEG 57.29577951308232f
#endif
#ifndef DEG_TO_RAD
#define DEG_TO_RAD 0.017453292519943295f
#endif

extern uint32_t sim_millis;
inline uint32_t millis() { return sim_millis; }
inline void delay(uint32_t ms) { sim_millis += ms; }

// Simulated wall clock: hour set by the simulator (-1 = not synced).
extern int sim_hour;
inline void configTzTime(const char*, const char*, const char* = nullptr, const char* = nullptr) {}
inline bool getLocalTime(struct tm* t, uint32_t = 5000) {
  if (sim_hour < 0) return false;
  *t = {};
  t->tm_hour = sim_hour;  // fixed date for snapshots: Sat 7 Nov
  t->tm_min = 42;
  t->tm_wday = 6;
  t->tm_mday = 7;
  t->tm_mon = 10;
  t->tm_yday = 310;
  return true;
}

class String {
 public:
  String() = default;
  String(const char* s) : s_(s ? s : "") {}
  String(const std::string& s) : s_(s) {}
  String(char c) : s_(1, c) {}
  String(int v) : s_(std::to_string(v)) {}
  String(unsigned v) : s_(std::to_string(v)) {}
  String(long v) : s_(std::to_string(v)) {}
  String(unsigned long v) : s_(std::to_string(v)) {}
  String(double v, unsigned digits = 2) {
    char b[32];
    snprintf(b, sizeof b, "%.*f", digits, v);
    s_ = b;
  }
  String(float v, unsigned digits = 2) : String(static_cast<double>(v), digits) {}
  const char* c_str() const { return s_.c_str(); }
  unsigned length() const { return s_.size(); }
  bool isEmpty() const { return s_.empty(); }
  String substring(unsigned a) const { return a >= s_.size() ? String() : String(s_.substr(a)); }
  String substring(unsigned a, unsigned b) const {
    if (a >= s_.size() || b <= a) return String();
    return String(s_.substr(a, b - a));
  }
  void remove(unsigned i) { if (i < s_.size()) s_.erase(i); }
  void trim() {
    auto a = s_.find_first_not_of(" \t\r\n");
    auto b = s_.find_last_not_of(" \t\r\n");
    s_ = a == std::string::npos ? "" : s_.substr(a, b - a + 1);
  }
  bool reserve(unsigned n) { s_.reserve(n); return true; }
  String& operator+=(const String& o) { s_ += o.s_; return *this; }
  String& operator+=(const char* o) { s_ += o; return *this; }
  bool operator==(const String& o) const { return s_ == o.s_; }
  friend String operator+(const String& a, const String& b) { return String(a.s_ + b.s_); }
  friend String operator+(const String& a, const char* b) { return String(a.s_ + b); }
  friend String operator+(const char* a, const String& b) { return String(std::string(a) + b.s_); }

 private:
  std::string s_;
};

struct SerialShim {
  void begin(int) {}
  void println(const char* s = "") { std::printf("%s\n", s); }
  void println(const String& s) { println(s.c_str()); }
  void printf(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::vprintf(fmt, ap);
    va_end(ap);
  }
};
extern SerialShim Serial;

struct EspShim {
  uint32_t getFreeHeap() { return 100000; }
  uint32_t getMinFreeHeap() { return 100000; }
  uint32_t getMaxAllocHeap() { return 60000; }
};
extern EspShim ESP;

// FreeRTOS: single-threaded simulator, everything succeeds immediately.
typedef void* SemaphoreHandle_t;
typedef void* TaskHandle_t;
#define portMAX_DELAY 0xFFFFFFFFu
#define pdTRUE 1
#define pdMS_TO_TICKS(ms) (ms)
inline SemaphoreHandle_t xSemaphoreCreateMutex() { static int m; return &m; }
inline int xSemaphoreTake(SemaphoreHandle_t, uint32_t) { return pdTRUE; }
inline int xSemaphoreGive(SemaphoreHandle_t) { return pdTRUE; }
inline uint32_t ulTaskNotifyTake(int, uint32_t) { return 1; }
inline void xTaskNotifyGive(TaskHandle_t) {}
inline void vTaskDelay(uint32_t ms) { sim_millis += ms; }
inline uint32_t uxTaskGetStackHighWaterMark(TaskHandle_t) { return 0; }
inline int xTaskCreatePinnedToCore(void (*)(void*), const char*, uint32_t, void*, int, TaskHandle_t* h, int) {
  static int t;
  if (h) *h = &t;
  return 1;
}
