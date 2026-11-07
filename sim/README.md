# Desktop simulator

Compiles the real firmware (`../src/main.cpp`) natively against M5GFX + SDL2,
with shims for Arduino, Wi-Fi, HTTP and FreeRTOS (`shim/`). Needs SDL2:
`brew install sdl2` (macOS) or `apt install libsdl2-dev` (Linux). Flags come
from `sdl2-config`.

All commands run from `sim/`.

## Headless renders (`env:sim`)

```sh
pio run -e sim
mkdir -p out && .pio/build/sim/program fixtures/aircraft.json out
python3 contact_sheet.py out        # optional: round-masked sheets (macOS font path)
```

`src/sim.cpp` sets UI state directly and writes one PNG per scenario.
`fixtures/aircraft.json` is a frozen feed, so renders are deterministic.

## Live window (`env:sim-live`)

```sh
pio run -e sim-live
.pio/build/sim-live/program [feed.json]   # default fixtures/aircraft.json
```

Runs the firmware's own `setup()`/`loop()` in a 2x M5Dial-framed window, with
real-time `millis()`. The feed is served by the HTTP shim on every fetch, after
a 400 ms fake latency.

| Input | Device |
|---|---|
| Mouse click on screen | Touch tap |
| Left / Right arrow, mouse wheel | Encoder, one detent (4 counts) |
| Space (hold) | Button A, press/release in real time (click < 500 ms, refresh at 1.2 s; arrows work while held) |
| W | Toggle Wi-Fi connected / disconnected |
| F | Toggle HTTP 200 / 503 |
| Esc, Q | Quit |

Options: `--quit-after SECONDS` and `--shot out.png` save the final frame on exit
(used for smoke tests).

## Baseline comparison

```sh
python3 -I compare.py                 # out/*.png vs baseline/, diffs in out/diff/, exit 1 on change
python3 -I compare.py --threshold 0   # flag any differing pixel (default 50 px, --tol 8 per channel)
python3 -I compare.py --update        # accept current renders as the new baseline
```

CI (`.github/workflows/firmware.yml`) builds the firmware and both sim envs,
renders the fixture, runs `compare.py` and uploads `out/` as the `sim-renders`
artifact.
