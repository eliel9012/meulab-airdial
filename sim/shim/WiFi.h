#pragma once
#include <Arduino.h>
#define WIFI_STA 1
enum { WL_IDLE_STATUS = 0, WL_CONNECTED = 3, WL_DISCONNECTED = 6 };
struct WiFiShim {
  int state = WL_CONNECTED;  // simulator controls this
  void mode(int) {}
  void setSleep(bool) {}
  void setAutoReconnect(bool) {}
  void begin() {}
  void begin(const char*, const char*) {}
  int status() { return state; }
};
extern WiFiShim WiFi;

// Stream over an in-memory buffer (the simulated HTTP body).
class WiFiClient {
 public:
  std::string data;
  size_t pos = 0;
  int available() { return static_cast<int>(data.size() - pos); }
  int read() { return pos < data.size() ? static_cast<unsigned char>(data[pos++]) : -1; }
  int read(uint8_t* b, size_t n) {
    size_t k = std::min(n, data.size() - pos);
    memcpy(b, data.data() + pos, k);
    pos += k;
    return static_cast<int>(k);
  }
  bool connected() { return false; }  // server already closed; drain buffer
};
