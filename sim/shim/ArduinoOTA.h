#pragma once
// Simulator stub: OTA never runs on desktop.
#include <functional>
typedef int ota_error_t;
struct ArduinoOTAShim {
  void setHostname(const char*) {}
  void setPassword(const char*) {}
  void onStart(std::function<void()>) {}
  void onEnd(std::function<void()>) {}
  void onProgress(std::function<void(unsigned int, unsigned int)>) {}
  void onError(std::function<void(ota_error_t)>) {}
  void begin() {}
  void handle() {}
};
inline ArduinoOTAShim ArduinoOTA;
