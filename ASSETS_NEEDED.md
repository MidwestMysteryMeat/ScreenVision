# Assets needed

**Short answer: no media assets. None at all. There is nothing to download or place.**

ScreenVision ships zero image, audio, font, and video files, and it never reads a
media file from disk. The whole repo is seven text files (`.gitignore`, `LICENSE`,
`README.md`, `requirements.txt`, `screen_vision.py`, `snap_server.py`,
`tests/test_screenvision.py`, plus `.github/FUNDING.yml`). Verified against both the
working tree and full git history — no media file has ever been committed.

There are **no unguarded load sites**: the codebase contains no builtin `open()`, no
`pathlib`/`os.path` use, and no `__file__` handling. Every image exists only as an
in-memory `io.BytesIO` buffer.

| path/pattern | type | format | dimensions | used for | required/optional | fallback behavior |
|---|---|---|---|---|---|---|
| — | — | — | — | *no repo media assets exist* | — | — |

## Why there is nothing to supply

Images are **captured live, not loaded**:

- `snap_server.py:144` — `shot = sct.grab(mon)` grabs the screen via `mss`
- `snap_server.py:145-147` — wrapped with `Image.frombytes(...)` and saved as JPEG into
  a `BytesIO`, returned as the HTTP response body (no file written)
- `screen_vision.py:132-134` — the GPU host decodes that HTTP response with
  `Image.open(io.BytesIO(data))` — a buffer, not a path
- `screen_vision.py:139-140` — re-encoded and base64'd for the Ollama request
- `screen_vision.py:366-370` — Graph mode renders a matplotlib plot to `BytesIO`
- `snap_server.py:214-215` — the tray indicator icons are **generated** as solid 64×64
  colours (`PImage.new("RGB",(64,64),(40,160,60))` / `(210,40,40)`), not loaded `.ico`s
- `tests/test_screenvision.py:53-55` — the test image is `Image.new("RGB", (2,2), "black")`
  into a `BytesIO`; there is no fixtures directory

No fonts are needed either. There is no `ImageFont`, no `ImageFont.truetype`, and no
`ImageDraw` anywhere — the only text rendering is matplotlib's own
(`screen_vision.py:354`, `screen_vision.py:364`), which uses the DejaVu Sans font
bundled inside the `matplotlib` wheel. No system font, no `.ttf` in the repo.

`.gitignore` does not list `*.png` or a `screenshots/`-style directory. That is not an
omission — the program writes **no** files to disk, so there are no capture artifacts
to ignore.

---

## What you DO need: a vision model (a runtime dependency, not a repo file)

This is the thing most likely to be mistaken for a missing asset. If ScreenVision
cannot see your screen, the cause is the model or the network — **never a file absent
from this repo.**

| what | value | where it's set | how to satisfy it |
|---|---|---|---|
| Ollama server | `http://localhost:11434` | `screen_vision.py:8` (hardcoded constant) | install and run Ollama on the GPU host |
| Vision model | `qwen3vl-32b-instruct` | `screen_vision.py:9` (hardcoded constant) | `ollama pull qwen3vl-32b-instruct` — or any vision model, then edit the constant |
| Target PC URL | `http://TARGET_PC_IP:8765/snap` (placeholder) | `screen_vision.py:7` (hardcoded constant) | edit to your capture machine's IP |

**Config is edit-the-source, not env vars** (`README.md:175`). `OLLAMA`, `MODEL`, and
`SNAP_URL` are module-level constants with no environment-variable or config-file
override. The `SCREENVISION_*` env vars that do exist (`AGREE`, `TOKEN`, `UI_BIND`,
`UI_USER`, `UI_PASS`, `AUTO_MAX_MIN`, `BIND`) cover consent, auth, and binding only.

Failure modes are graceful — nothing crashes on a missing model:

- Ollama down → `🔌 Ollama unreachable: <err>` (`screen_vision.py:468-471`)
- model not pulled → `/api/generate` returns 404, surfaced as
  `❌ Load failed: HTTP Error 404: Not Found` (`screen_vision.py:494-497`)
- inference error → `[Error: <err>]` (`screen_vision.py:211-212`)
- AUTO loop error → recorded in status and the loop continues (`screen_vision.py:544-546`)
- graph render error → `[graph render failed: <err>]` (`screen_vision.py:423-424`)

Note that `gpu_status()` reports model **residency**, not installation
(`screen_vision.py:487-488`) — it won't tell you the model is missing until you press
Load or Send.

## Other runtime dependencies (all pip, no binaries)

- GPU host: `gradio`, `pillow`, `numpy`, `matplotlib`
- Target PC: `pillow`, `mss`
- Optional: `pystray` for the capture-indicator tray icon — degrades cleanly, printing
  "Tray indicator unavailable" and running HTTP-only (`snap_server.py:205-212`,
  `snap_server.py:249-255`)

No tesseract/OCR, no ffmpeg, no native GUI toolkit (the UI is served in a browser by
Gradio on `127.0.0.1:7862`). See `README.md:103-131` for the full setup — note that
**not one step is "download or place a file."**
