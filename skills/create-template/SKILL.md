---
name: create-template
description: Create or modify a music-video template for avp — the JSON layer spec (background, waveform/spectrum/bars, logo, title text, lyric placement) that render-music-video turns into a video. Use when the user says "make a new template", "change the layout", "move the logo", "different visualizer", "a template for Instagram/square", or wants a house style saved for reuse.
---

# Create a template

A template is a JSON file listing avp layers bottom → top, with placeholders filled per render. `render.py` compiles it to an avp project every run, so templates stay readable and diffable; nothing is stored in avp's GUI.

Script location: see `install-avp` ("Script location"). Full field reference: `$ROOT/docs/template-format.md`. Start by copying the closest built-in from `$ROOT/templates/`:

| Template | Size | Look |
|---|---|---|
| `waveform-center` | 1920×1080 | scrolling waveform across the middle, logo top-left, title/artist bottom-left |
| `spectrum-bars` | 1920×1080 | frequency bars rising from the bottom in brand primary, title top-left, logo top-right |
| `logo-pulse` | 1920×1080 | logo centre pulsing to the beat inside mirrored bars, title centred low |
| `vertical-short` | 1080×1920 | 9:16 for Shorts/Reels/TikTok/status, logo top, waveform middle, title lower third |

## Where to save it

- A project's own template: `<project>/avp-templates/<name>.json`, rendered with `-t avp-templates/<name>.json`.
- A template that should ship with the plugin: `$ROOT/templates/<name>.json` (then commit to the plugin repo).

## Workflow

1. Copy the nearest built-in and edit layers. Units are what avp's GUI shows: pixels at the template's `output` size, `%` for scale/opacity, combo boxes by their label. Numbers can be expressions in `W` and `H` (`"H*0.86"`, `"W/2"`, `"W-40"`), so a template stays correct under `--size`.
2. `--dry-run` to see the resolved spec (placeholders filled, images converted and placed):
   ```bash
   python3 "$ROOT/scripts/render.py" song.mp3 -t my.json --dry-run
   ```
3. Render a short preview and look at frames, not just the exit code:
   ```bash
   python3 "$ROOT/scripts/render.py" song.mp3 -t my.json --preview 8 -p compat -o /tmp/p.mp4
   ffmpeg -v error -ss 4 -i /tmp/p.mp4 -frames:v 1 /tmp/p.png     # then view it
   ```
   With lyrics, add `--subs … --karaoke` and check they clear the title and logo; tune the template's `"lyrics"` block.
4. Iterate until the user is happy.

## avp limitations to design around (verified with avp 2.2.4)

- **Waveform layers must stay full-frame.** `scale` below 100 crashes the render (`ValueError: images do not match`), and `x`/`y` offsets wrap the waveform around the frame instead of moving it. Position other layers around a full-frame waveform; for a bottom-anchored look use `mode: "Frequency Bar"`, which grows up from the bottom edge.
- **Classic Visualizer** has real layouts (`Classic` centred mirrored, `Split`, `Bottom`, `Top`) plus `scale` (bar height) and `y`. It's the way to get a bars strip at a chosen height.
- **No blur/darken in avp.** Image layers take `"blur"` (px) and `"darken"` (0–1), which `render.py` applies with ffmpeg before avp sees the image, and `"cover": true` to fill and crop to the frame.
- **Logos:** give `"fit": [w, h]` (a pixel box) and `"anchor"` (`top-left`, `top-right`, `bottom-left`, `bottom-right`, `top-center`, `bottom-center`, `center`) + `"margin"`. avp's own image `scale` is relative to the source image's pixel size, which differs per logo file, so don't rely on it.
- **Left-aligned text** crashes avp 2.2.4; the project builder converts it to centred text at the right offset automatically, so `"alignment": "Left"` is safe to use.
- `"if": "<var>"` / `"if": "!<var>"` skips a layer when a variable is empty — templates use it for logo/background/artist fallbacks.

## Components and their settings

`image`, `video`, `color`, `text`, `waveform`, `spectrum`, `classic`, `sound`, `life`. The builder rejects an unknown setting and lists the valid ones, so a typo fails loudly. Combo labels:

- waveform `mode`: `Frequency Line`, `Frequency Bar`, `Cline`, `Line`; `amplitude`: `Logarithmic`, `Square root`, `Cubic root`, `Linear`; also `color`, `opacity`, `mono`, `mirror`, `compress`, `speed` (blend smoothing, 100 = none).
- spectrum `filterType`: `Spectrum`, `Histogram`, `Vector Scope`, `Musical Scale`, `Phase`; `color`: `Channel`, `Intensity`, `Rainbow`, `Moreland`, `Nebulae`, `Fire`, `Fiery`, `Fruit`, `Cool`.
- classic `layout`: `Classic`, `Split`, `Bottom`, `Top`; `visColor`, `scale`, `y`, `bars`.
- text: `title`, `font` (family or font file), `fontSize`, `fontStyle` (`Normal`, `Semi-Bold`, `Bold`, `Italic`, `Bold Italic`, `Faux Italic`, `Small Caps`), `textColor`, `alignment` (`Left`, `Middle`, `Right`), `xPosition`, `yPosition`, `shadow`, `stroke`, `strokeColor`.
- image: `image`, `scale`, `x`, `y`, `rotate`, `mirror`, `respondToAudio` (pulse), `sensitivity`, `color` (saturation %).
- color: `color1`, `color2`, `fillType` (`Solid`, `Linear Gradient`, `Radial Gradient`), `width`, `height`, `x`, `y`.
- video: `video`, `loop`, `scale`, `x`, `y`, `useAudio`.
