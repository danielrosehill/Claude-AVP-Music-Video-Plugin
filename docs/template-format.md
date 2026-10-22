# Template format

A template is a JSON file. `scripts/render.py` resolves it against the brand
manifest and per-render variables, then `scripts/avp_project.py` compiles the
result into an avp project (`.avp`) for that one render.

```json
{
  "description": "One line shown to the user when choosing a template",
  "output": { "width": 1920, "height": 1080, "fps": 30 },
  "lyrics": { "position": "bottom", "margin_v": "H*0.20", "size": "H*0.06" },
  "layers": [
    { "if": "background_image", "component": "image", "cover": true,
      "blur": 12, "darken": 0.45, "set": { "image": "{{background_image}}" } },
    { "if": "!background", "component": "color",
      "set": { "color1": "{{brand.colors.background|#14142b}}",
               "color2": "{{brand.colors.secondary|#3a2160}}",
               "fillType": "Linear Gradient" } },
    { "component": "waveform",
      "set": { "mode": "Cline", "mono": true, "amplitude": "Linear",
               "color": "{{brand.colors.waveform|#ffffff}}", "opacity": 60 } },
    { "if": "brand.logo", "component": "image",
      "fit": ["W*0.14", "H*0.12"], "anchor": "top-left", "margin": "H*0.05",
      "set": { "image": "{{brand.logo}}" } },
    { "component": "text",
      "set": { "title": "{{title}}", "font": "{{brand.font.file|DejaVu Sans}}",
               "fontStyle": "Bold", "fontSize": "H*0.06", "alignment": "Left",
               "xPosition": "H*0.05", "yPosition": "H*0.86",
               "textColor": "{{brand.colors.text|#ffffff}}", "shadow": true } }
  ]
}
```

## Top level

| Key | Meaning |
|---|---|
| `output` | default frame size and fps; `--size` / `--fps` override per render |
| `lyrics` | default placement for burned-in lyrics (`position`, `margin_v`, `size`, any `lyrics_to_ass.py` style key); `--subs-style` overrides |
| `layers` | bottom → top (first entry is the background) |

## Layer keys

| Key | Meaning |
|---|---|
| `component` | `image`, `video`, `color`, `text`, `waveform`, `spectrum`, `classic`, `sound`, `life` |
| `set` | avp settings for that component (see `skills/create-template/SKILL.md` for names) |
| `if` | `"var"` keeps the layer only when the variable is non-empty; `"!var"` only when empty |
| `fit` | image only: `[w, h]` pixel box the image is scaled into (aspect kept) |
| `anchor` / `margin` | image only: place the fitted image (`top-left`, `top-right`, `bottom-left`, `bottom-right`, `top-center`, `bottom-center`, `center`) |
| `cover` | image only: `true` scales and crops to fill the frame |
| `blur` / `darken` | image only: gaussian blur sigma (px) / darken 0–1, applied by ffmpeg before avp |

## Values

- **Placeholders:** `{{name}}` or `{{name|default}}`. Variables: `title`, `artist`, `subtitle`
  (from flags, else the audio's tags, else the file name / brand name), `cover` (from `--cover`,
  else the art embedded in the audio), `background` (`--background` → `brand.background` →
  `cover`), `background_image` / `background_video` (that split by file type),
  `brand.*` (anything in `avp-brand.json`), `W`, `H`, and anything passed with `--var key=value`.
  A placeholder that fills the whole string keeps its JSON type (number, boolean).
- **Expressions:** numeric settings accept arithmetic in `W` and `H`: `"H*0.86"`, `"W/2"`,
  `"W-40"`, `"(W-600)/2"`. Only `+ - * / //`, numbers and `W`/`H` are allowed.
- **Units:** what avp's GUI shows: pixels at the output size; `%` for scale and opacity;
  combo boxes by label (case-insensitive) or index; colours as `#rrggbb`, `#rgb` or `r,g,b`.
- **Fonts:** a family name, or a path to a `.ttf`/`.otf` (installed for the user into
  `~/.local/share/fonts/avp-music-video/` on first use).
- **Images:** any format ffmpeg can read, plus SVG (via rsvg-convert / Inkscape / ImageMagick).
  Converted to PNG in the render's temp dir; the originals are never modified.
