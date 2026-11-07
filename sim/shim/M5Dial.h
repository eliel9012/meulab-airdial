#pragma once
#include <Arduino.h>
#include <M5GFX.h>

// Display = 240x240 sprite the simulator snapshots to PNG (headless) or blits
// to an SDL window (sim-live).
struct SimDisplay : public M5Canvas {
  void setBrightness(uint8_t) {}
};

// Input shims with M5Unified-like edge semantics. The host (simulator) sets the
// raw state (`raw`, Encoder `value`, Touch `x`/`y`); M5Dial.update() derives
// the edges once per loop. Defaults (raw=false) keep every query false, so the
// headless renderer needs no input handling.
constexpr uint32_t SIM_HOLD_MS = 500;  // M5Unified default hold threshold

struct SimButton {
  bool raw = false;  // host: physical button state

  void update(uint32_t now) {
    pressedEdge_ = raw && !pressed_;
    releasedEdge_ = !raw && pressed_;
    if (pressedEdge_) { since_ = now; held_ = false; }
    if (releasedEdge_) since_ = now;
    clicked_ = releasedEdge_ && !held_;
    holdEdge_ = raw && !held_ && now - since_ >= SIM_HOLD_MS;
    if (holdEdge_) held_ = true;
    pressed_ = raw;
    now_ = now;
  }
  bool isPressed() const { return pressed_; }
  bool isReleased() const { return !pressed_; }
  bool isHolding() const { return pressed_ && held_; }
  bool wasPressed() const { return pressedEdge_; }
  bool wasReleased() const { return releasedEdge_; }
  bool wasClicked() const { return clicked_; }  // released before the hold threshold
  bool wasHold() const { return holdEdge_; }
  bool wasReleasedAfterHold() const { return releasedEdge_ && held_; }
  bool pressedFor(uint32_t ms) const { return pressed_ && now_ - since_ >= ms; }
  bool releasedFor(uint32_t ms) const { return !pressed_ && now_ - since_ >= ms; }

 private:
  bool pressed_ = false, held_ = false;
  bool pressedEdge_ = false, releasedEdge_ = false, clicked_ = false, holdEdge_ = false;
  uint32_t since_ = 0, now_ = 0;
};

struct SimTouchDetail {
  int x = -1, y = -1;
  bool pressed = false, pressedEdge = false, releasedEdge = false, clicked = false;
  bool isPressed() const { return pressed; }
  bool isReleased() const { return !pressed; }
  bool wasPressed() const { return pressedEdge; }
  bool wasReleased() const { return releasedEdge; }
  bool wasClicked() const { return clicked; }  // short tap
};
struct SimTouch {
  bool raw = false;  // host: finger down
  int x = -1, y = -1;
  void update(uint32_t now) {
    btn_.raw = raw;
    btn_.update(now);
    detail_.x = x;
    detail_.y = y;
    detail_.pressed = btn_.isPressed();
    detail_.pressedEdge = btn_.wasPressed();
    detail_.releasedEdge = btn_.wasReleased();
    detail_.clicked = btn_.wasClicked();
  }
  SimTouchDetail getDetail() const { return detail_; }
  uint8_t getCount() const { return detail_.pressed ? 1 : 0; }

 private:
  SimButton btn_;
  SimTouchDetail detail_;
};

struct SimEncoder {
  long value = 0;  // host: raw quadrature count (4 per detent)
  long read() const { return value; }
  void write(long v) { value = v; }
  long readAndReset() { long v = value; value = 0; return v; }
};
struct SimSpeaker { void setVolume(uint8_t) {} void tone(uint32_t, uint32_t) {} };
struct SimConfig {};
struct SimM5 { SimConfig config() { return {}; } };
extern SimM5 M5;
struct SimDial {
  SimDisplay Display;
  SimButton BtnA;
  SimTouch Touch;
  SimEncoder Encoder;
  SimSpeaker Speaker;
  void begin(SimConfig, bool, bool) {
    Display.setColorDepth(16);
    Display.createSprite(240, 240);
  }
  void update() {
    uint32_t now = millis();
    BtnA.update(now);
    Touch.update(now);
  }
};
extern SimDial M5Dial;
