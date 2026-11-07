#pragma once
#include <WiFi.h>
// Simulator: setup portal is a no-op that stays "active" until stopped.
class WiFiManager {
 public:
  void setConfigPortalBlocking(bool) {}
  void setConfigPortalTimeout(unsigned long) {}
  bool startConfigPortal(const char*) { active_ = true; return false; }
  bool process() { return false; }
  bool getConfigPortalActive() { return active_; }
  void stopConfigPortal() { active_ = false; }

 private:
  bool active_ = false;
};
