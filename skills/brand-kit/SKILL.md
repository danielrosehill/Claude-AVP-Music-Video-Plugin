---
name: brand-kit
description: Discover a project's brand assets — logo, background art, brand colours, brand font — in a repository and save them as an avp-brand.json manifest that the music-video templates read. Use when the user says "use our brand assets", "find the logo in this repo", "set up branding for the music videos", "make a brand kit", or before the first render-music-video in a project that has no avp-brand.json yet.
---

# Brand kit → `avp-brand.json`

The templates are brand-agnostic; everything brand-specific comes from one small manifest at the project root. This skill finds candidates, picks sensibly, confirms with the user only where it is genuinely ambiguous, and writes the file.

Script location: see `install-avp` ("Script location") — `$ROOT/scripts/…`.

## 1. Look for an existing manifest first

If `avp-brand.json` (or `brand/avp-brand.json`) exists, read it, check every path in it still exists, and stop unless the user wants changes.

## 2. Scan

```bash
python3 -I "$ROOT/scripts/find_brand_assets.py" <repo-root> --max 8
```

Returns JSON with ranked `logos`, `backgrounds`, `fonts` (ttf/otf with family names), `webfonts_need_conversion`, `css_font_families`, `colors` (hex + the variable names they were declared under, e.g. `--brand-primary`), and any `manifests` (brand.json / design-tokens.json …) the repo already has — read those, they beat guessing from CSS.

The scanner ranks; it does not decide. Look at the actual files before choosing:
- **Logo:** view the top candidates (Read the image). Prefer SVG or a large transparent PNG; prefer the horizontal wordmark for 16:9 and the square mark for `logo-pulse`. Logos on a dark video background need the light/inverted variant if the repo has one (`logo-white`, `logo-dark-bg`, `-inverse`) — put that in `logo` and the other in `logo_alt`.
- **Colours:** name-hinted variables (`primary`, `brand`, `accent`) beat frequency. Ignore pure greys and `#fff`/`#000` for `primary`. Check contrast: `text` must read on `background`.
- **Font:** a ttf/otf from the repo, preferably a bold/display weight for titles. If the brand font only exists as woff2, convert it (`pip install fonttools brotli`, then `fonttools ttLib.woff2 decompress in.woff2`), or fall back to an installed family by name.
- **Background:** optional. Without one, templates use the song's embedded cover art, then a gradient of `colors.background` → `colors.secondary`.

If the repo has no logo at all, say so and continue without one — templates skip the logo layer.

## 3. Write the manifest

Paths are relative to the manifest's own directory.

```json
{
  "name": "Acme Records",
  "logo": "public/brand/logo-white.svg",
  "logo_alt": "public/brand/logo-mark.png",
  "background": "public/images/hero.jpg",
  "font": { "file": "public/fonts/Inter-Bold.ttf" },
  "colors": {
    "primary": "#ff5a36",
    "secondary": "#2b1055",
    "background": "#0d0d1a",
    "text": "#ffffff",
    "waveform": "#ffffff"
  },
  "background_darken": 0.45,
  "background_blur": 12,
  "default_template": "waveform-center"
}
```

| Key | Used for |
|---|---|
| `logo` | logo layer in every template (any image; SVG/WebP converted automatically) |
| `background` | background image or looping video; per-render `--cover` / `--background` override it |
| `font.file` | title/artist text and karaoke lyrics; installed into `~/.local/share/fonts/avp-music-video/` on first render because avp resolves fonts by family name |
| `colors.primary` | artist line, spectrum bars, karaoke highlight |
| `colors.text` | title, unsung lyrics |
| `colors.waveform` | waveform / classic bars (default white) |
| `colors.background` / `secondary` | gradient used when there is no background art |
| `background_darken` (0–1), `background_blur` (px) | legibility of text over busy art |
| `default_template` | used when render is called without `-t` |

Any extra key is available to templates as `{{brand.<key>}}`.

## 4. Check it

```bash
python3 "$ROOT/scripts/render.py" <some-audio> --brand avp-brand.json --dry-run
```

Every image path in the printed spec must resolve. Then hand over to `render-music-video` with `--preview 10` so the user sees the brand applied before a full render.

Whether to commit `avp-brand.json` is the user's call; it contains only paths and colours.
