[![Claude Code View Marketplace](https://img.shields.io/badge/Claude%20Code-View%20Marketplace-blue?style=for-the-badge&logo=github)](https://github.com/danielrosehill/Claude-Code-Plugins)

# avp-music-video

A Claude Code plugin that turns an audio file into a branded music video with
**[audio-visualizer-python](https://github.com/djfun/audio-visualizer-python)** (`avp`),
the layer-based audio-to-video renderer (image / video / gradient / text /
waveform / spectrum / bars → MP4 via ffmpeg).

The use case it was built for: you have a song (say an MP3 from Suno), a project
repo with a logo and brand colours, and you want a small, good-looking music video
with those brand assets on it, optionally with karaoke lyrics, without opening an
editor.

```
song.mp3 + avp-brand.json + template ─► avp (headless) ─► ffmpeg: lyrics + HEVC/AV1 ─► song.waveform-center.mp4
```

Part of the [danielrosehill Claude Code marketplace](https://github.com/danielrosehill/Claude-Code-Plugins).

```bash
/plugin marketplace add https://github.com/danielrosehill/Claude-Code-Plugins
/plugin install avp-music-video@danielrosehill
```

## Skills

| Skill | What it does |
|---|---|
| `install-avp` | Installs avp (`uv tool` / `pipx`), ffmpeg and Qt runtime libs; verifies a headless render |
| `brand-kit` | Scans a repo for logos, backgrounds, brand colours and fonts; writes `avp-brand.json` |
| `render-music-video` | Audio → MP4 from a template, with title/artist from tags, cover art from the file, and a space-efficient final encode |
| `karaoke-lyrics` | LRC / enhanced LRC / SRT / ASS, or plain lyrics aligned with Whisper → burned-in karaoke sweep or plain subtitles |
| `create-template` | Author or modify a JSON layer template and preview it |

## Templates

| Template | Size | Look |
|---|---|---|
| `waveform-center` | 1920×1080 | scrolling waveform across the middle, logo top-left, title/artist bottom-left |
| `spectrum-bars` | 1920×1080 | frequency bars in the brand colour rising from the bottom |
| `logo-pulse` | 1920×1080 | logo centred and pulsing to the beat inside mirrored bars |
| `vertical-short` | 1080×1920 | 9:16 for Shorts / Reels / TikTok / status |

Templates are plain JSON, documented in [`docs/template-format.md`](docs/template-format.md).
They are brand-agnostic: logo, colours, font and background come from `avp-brand.json`,
and each layer has a fallback when an asset is missing.

## Scripts (usable without Claude)

```bash
python3 scripts/render.py song.mp3 -t waveform-center --brand avp-brand.json \
  --subs lyrics.lrc --karaoke -p small            # full render
python3 scripts/render.py song.mp3 --preview 10    # 10-second look, 1/3 into the track
python3 scripts/find_brand_assets.py path/to/repo  # brand candidates as JSON
python3 scripts/lyrics_to_ass.py lyrics.lrc out.ass --karaoke
```

Only Python's standard library is needed outside avp itself.

## Output size

The final encode is a single ffmpeg pass that also burns the lyrics. The source
audio is stream-copied (no re-encode for MP3/AAC), so file size is almost all video.
Profiles, measured in [`docs/encoding-benchmark.md`](docs/encoding-benchmark.md):

| `-p` | Codec | 30 s 1080p clip | When |
|---|---|---|---|
| `small` (default) | AV1 CRF 40 | 9.3 MB, VMAF 96.3 | YouTube, web, modern devices |
| `smallest` | AV1 CRF 44 | 7.2 MB, VMAF 95.2 | smallest still-clean file |
| `compat` | H.264 CRF 23 | 15.8 MB, VMAF 96.0 | anything that can't play AV1 |
| `hevc` | H.265 CRF 28 | 10.5 MB, VMAF 93.9 | HEVC-but-not-AV1 players (older Apple devices) |

AV1 matches H.264's quality at about 59% of the size, for roughly twice the encode time.
x265 `slow` was barely smaller than H.264 at 4× the time, so it isn't a profile.

## avp quirks handled for you

avp 2.2.4 has a few render bugs. This plugin works around them and documents them in
[`docs/avp-internals.md`](docs/avp-internals.md): left-aligned text crashes, and the
waveform is nearly invisible at 1080p (ffmpeg `showwaves draw=scale`). Each render also
runs in an isolated avp config dir, so your GUI settings are never changed.

## License

MIT. avp itself is MIT; some of its dependencies (PyQt6) are GPL.
