# avp internals: what this plugin relies on

Reverse-engineered from audio-visualizer-python **2.2.4** (PyPI, released 2026-02-12;
source `djfun/audio-visualizer-python`, `src/avp/`) with PyQt6 6.11, Pillow 13,
ffmpeg 8.0.1 on Ubuntu, verified 2026-10-22. Re-check after upgrading avp.

## Headless commandline mode

- `avp [project] -c LAYER NAME [args…] -i AUDIO -o OUT` exports and exits. More
  than one argv, or one starting with `-`, selects commandline mode (`cli.py`).
- It still creates a `QApplication`, so it needs a display or
  `QT_QPA_PLATFORM=offscreen`. Offscreen works fully; it prints
  `WARNING: Failed to connect QFontComboBox`, which is harmless.
- Only some components accept CLI args (`classic`: color/layout/scale/y; `image`:
  path; `text`: title/color/size/x/y; `video`: path/audio; `color`: color;
  `sound`: path). **Waveform and Spectrum accept none**: they can only be
  configured through a preset or a project file. That's why this plugin compiles
  projects instead of passing `-c` flags.
- Speed: 1080p30 renders at roughly real time on a 16-thread laptop. The final
  re-encode is extra (see encoding-benchmark.md).

## Config and settings

- Data dir = `QStandardPaths.AppConfigLocation/audio-visualizer`, which on Linux
  honours `XDG_CONFIG_HOME` (default `~/.config/audio-visualizer`). It holds
  `settings.ini` (QSettings INI), `presets/`, `projects/`, `log/`.
- Output resolution, fps, codec, bitrate and x264 preset are **global settings**
  (`outputWidth`, `outputHeight`, `outputFrameRate`, `outputVideoBitrate` kbps,
  `outputPreset`, `outputVideoCodec`, `outputContainer` …), not per-project.
  render.py gives every render its own `XDG_CONFIG_HOME` in a temp dir, so the
  user's GUI settings are never touched and parallel renders don't collide.
- avp's encoder is bitrate-based H.264 only (no CRF). We use it for a 16 Mbps
  `veryfast` intermediate and do the real encode ourselves.

## Project files (.avp)

Plain text:

```
[Components]
<Component name>        # e.g. "Title Text", "Waveform"
<component version>     # e.g. 2
OrderedDict({...})      # the component's preset dict (Python literal)
...
[Settings]
projectDir=...
```

- Components are listed **top layer first**. The builder inserts each spec layer at
  index 0, so spec order (bottom → top) comes out right.
- "Relative" widget values (positions, font size, image scale …) are stored as a
  fraction of the frame width/height, not pixels. Hand-writing these is
  error-prone; the builder sets the GUI widgets in pixels and lets avp's own
  `createProjectFile` do the conversion.
- Default component colours are **random** per instance. Always set colours explicitly.

## Bugs found and how we work around them

| Bug (avp 2.2.4) | Symptom | Workaround | Remove when |
|---|---|---|---|
| `Text.getXY` handles alignment 1 and 2 only | `ValueError: Alignment value 0 unknown` for Left text | `avp_project.py` `left_align_workaround`: switch to Middle, shift x by half the text width (QFontMetrics) | upstream handles 0 |
| Waveform `showwaves` uses ffmpeg's default `draw=scale` | waveform nearly invisible at 1080p (mean alpha 16 at 1080p vs 56 at 720p); `draw=full` gives 84 / 91 | `scripts/avp_run.py` patches `Waveform.makeFfmpegFilter` to add `draw=full`; render.py runs avp through it | upstream sets/exposes `draw` |
| Waveform with `scale` ≠ 100 | `ValueError: images do not match` at frame 0 (`_currImage` full-frame vs scaled `baseImage`) | templates keep waveform full-frame; documented in create-template | upstream fix |
| Waveform `y`/`x` offset | waveform wraps around instead of moving | same | upstream fix |

Wrong turn, for the record: the 1080p waveform dimness looked like sample sparsity
(1,470 samples per frame at 44.1 kHz/30 fps vs 1,920 columns). Feeding avp a 96 kHz
resample made the trace denser but no brighter. Measuring the alpha channel of a bare
`showwaves` frame at both sizes and both `draw` modes isolated it.

## Formats

- Image component accepts `png jpg tif tiff gif bmp ico xbm xpm` (`Core.imageFormats`):
  **not** svg, webp or `.jpeg`. render.py converts everything else to PNG.
- Text fonts are resolved by **family name** via fontconfig at render time. A font
  registered only inside the builder process is lost, so render.py installs brand
  font files into `~/.local/share/fonts/avp-music-video/` and runs `fc-cache`.
