---
name: install-avp
description: Install and verify audio-visualizer-python (avp), the CLI this plugin renders music videos with, plus ffmpeg and the Qt runtime libraries it needs to run headless. Use when the user says "install avp", "set up the audio visualizer", "get the music video tool working", or when any other avp-music-video skill finds `avp` missing or failing.
---

# Install avp

[audio-visualizer-python](https://github.com/djfun/audio-visualizer-python) (`avp`, MIT, on PyPI as `audio-visualizer-python`) layers components — image, video, colour/gradient, text, waveform, spectrum, classic bars — over an audio file and exports a video through ffmpeg. It is a Qt app with a commandline mode; this plugin runs it offscreen.

## Script location

Every skill in this plugin uses the scripts in the plugin's `scripts/` folder:

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.cache/avp-music-video-plugin}"
[ -f "$ROOT/scripts/render.py" ] || git clone --depth 1 \
  https://github.com/danielrosehill/Claude-AVP-Music-Video-Plugin "$ROOT"
```

## Steps

1. **Check what's there**
   ```bash
   command -v avp && QT_QPA_PLATFORM=offscreen avp --version   # avp starts Qt even for --version
   command -v ffmpeg ffprobe && ffmpeg -version | head -1
   python3 --version            # avp needs Python >= 3.12
   ```
   Confirm ffmpeg has the encoders the render profiles use:
   `ffmpeg -hide_banner -encoders | grep -E 'libx264|libx265|libsvtav1'`.
   The default profiles (`small`, `smallest`) need `libsvtav1`; without it render.py falls back to `compat` (H.264) and says so. `hevc` needs `libx265`. Ubuntu 24.04+/Debian 12+ ffmpeg packages include all three.

2. **System packages** (only what is missing):
   - Debian/Ubuntu: `sudo apt install ffmpeg libxcb-cursor0 fontconfig`
   - Fedora: `sudo dnf install ffmpeg xcb-util-cursor fontconfig`
   - Arch: `sudo pacman -S ffmpeg xcb-util-cursor fontconfig`
   - macOS: `brew install ffmpeg`
   For SVG logos, one of: `librsvg2-bin` (`rsvg-convert`), Inkscape, or ImageMagick.

3. **Install avp as an isolated tool** — prefer `uv`, then `pipx`, never into a system Python:
   ```bash
   uv tool install audio-visualizer-python      # or: pipx install audio-visualizer-python
   ```
   Upgrade later with `uv tool upgrade audio-visualizer-python`.

4. **Verify a headless render end to end** (this proves Qt offscreen, ffmpeg and the plugin's patches all work):
   ```bash
   T=$(mktemp -d)
   ffmpeg -v error -f lavfi -i "sine=f=220:d=4" -b:a 128k "$T/tone.mp3"
   python3 "$ROOT/scripts/render.py" "$T/tone.mp3" -t waveform-center \
     --title "Install check" -p compat -o "$T/check.mp4"
   ```
   Expect a JSON report with `"video_codec": "h264"` and a few hundred KB file. Clean up `$T`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` then `Aborted` | No display, and no offscreen platform set. This happens for **any** avp command, even `--version`. `render.py` sets `QT_QPA_PLATFORM=offscreen`; when calling `avp` by hand on a server/SSH session, export it yourself. |
| `libxcb-cursor.so.0: cannot open shared object file` | Install `libxcb-cursor0` (Debian/Ubuntu) / `xcb-util-cursor`. |
| `Could not find FFmpeg` | ffmpeg not on PATH. |
| `<AVP.Toolkit.Common> WARNING: Failed to connect QFontComboBox` | Harmless; printed on every run. |
| `avp not found on PATH` from render.py | `~/.local/bin` not on PATH after `uv tool install` — run `uv tool update-shell` or add it. |

Report: avp version, ffmpeg version, which encoders are available, and the check render's output line.
