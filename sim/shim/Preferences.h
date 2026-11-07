#pragma once
// Simulator stub: in-memory, always starts with defaults.
#include <cstdint>
class Preferences {
 public:
  bool begin(const char*, bool = false) { return true; }
  bool getBool(const char*, bool def = false) { return def; }
  uint8_t getUChar(const char*, uint8_t def = 0) { return def; }
  size_t putBool(const char*, bool) { return 1; }
  size_t putUChar(const char*, uint8_t) { return 1; }
};
