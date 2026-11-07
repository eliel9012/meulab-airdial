#pragma once
#include <WiFi.h>
#define HTTP_CODE_OK 200
// Simulator: GET returns sim_http_code and serves sim_http_body.
extern int sim_http_code;
extern std::string sim_http_body;
class HTTPClient {
 public:
  void useHTTP10(bool) {}
  void setTimeout(uint32_t) {}
  bool begin(WiFiClient& c, const char*) { client_ = &c; return true; }
  int GET() {
    client_->data = sim_http_body;
    client_->pos = 0;
    return sim_http_code;
  }
  int getSize() { return -1; }
  WiFiClient* getStreamPtr() { return client_; }
  void end() {}

 private:
  WiFiClient* client_ = nullptr;
};
