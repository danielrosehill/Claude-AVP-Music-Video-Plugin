---
name: render-music-video
description: Render an audio file (MP3/WAV/FLAC/M4A, e.g. a Suno song) into a branded music video MP4 with avp: background or cover art, animated waveform/spectrum/bars, logo, title and artist, optional burned-in karaoke lyrics, encoded as small as possible. Use when the user says "make a music video from this MP3", "render this song with our template", "audio to video", "visualizer video for this track", "make a YouTube/Shorts video of this song".
---

# Render a music video

Script location: see `install-avp` ("Script location"). If `avp` isn't installed, run `install-avp` first.

## Inputs to settle (ask only for what you can't infer)

| Input | Default / where it comes from |
|---|---|
| Audio | required |
| Template | `-t`; else `default_template` in `avp-brand.json`; else `waveform-center`. Built-ins: `waveform-center`, `spectrum-bars`, `logo-pulse`, `vertical-short` (9:16). `ls $ROOT/templates` plus any `avp-templates/` in the project. |
| Brand | `--brand`; else `./avp-brand.json`, `brand/avp-brand.json`. None in the project and the user mentioned brand assets → run `brand-kit` first. |
| Title / artist | `--title` / `--artist`; else the audio's ID3/metadata tags; else file name / brand name. Suno MP3s usually carry the song title. Check the dry run. |
| Cover art | `--cover`; else art embedded in the audio (Suno embeds it). Used as the background when the brand has none. |
| Lyrics | `--subs file --karaoke`, see `karaoke-lyrics` |
| Size / aspect | template's own; `--size 1080p|720p|4k|square|vertical|portrait|WxH` |
| Output | `-o`; default `<audio-name>.<template>.mp4` next to the audio |
| Profile | `-p small` (AV1, default). Ask only if the video is going somewhere AV1 may not play (WhatsApp to older phones, smart TVs, older Apple devices): then `compat` or `hevc`. |

## Steps

1. **Dry run.** Resolves the template, converts images, prints the layer spec. Read it: title/artist right? Logo and background found?
   ```bash
   python3 "$ROOT/scripts/render.py" song.mp3 -t waveform-center --dry-run
   ```
2. **Preview.** 10 s, a third of the way in (or `--start` at the chorus), then look at a frame:
   ```bash
   python3 "$ROOT/scripts/render.py" song.mp3 -t waveform-center --preview 10 -p compat -o /tmp/preview.mp4
   ffmpeg -v error -y -ss 5 -i /tmp/preview.mp4 -frames:v 1 /tmp/preview.png   # Read the PNG
   ```
   Check text legibility over the background, logo placement, and lyrics clearing the title. Show the user the frame. Skip the preview only if the user explicitly wants straight-to-final with a template they've already approved.
3. **Full render** with the same flags minus `--preview`. Expect roughly real time for avp at 1080p30, plus the final encode (benchmark table below): about 3× the song length in total with the default AV1 on a 16-thread laptop. Both stages run at `nice 10`, so the desktop stays responsive. `--nice 0` gives full priority; `--threads 4` caps the encoder for a lighter footprint. Run long tracks in the background.
4. **Report** from the JSON the script prints: output path, duration, size in MB, codec, whether audio was copied, timings. Mention the file is next to the audio unless `-o` said otherwise.

## Size: the final encode

avp renders a near-lossless intermediate (16 Mbps H.264). `render.py` then does one ffmpeg pass that burns lyrics and encodes with the chosen profile. The source audio is **stream-copied** when it is MP3/AAC/ALAC, so the song is never re-encoded; `--reencode-audio` forces AAC 192k.

| Profile | Codec | 30 s @1080p30, waveform template* | Encode time | Use when |
|---|---|---|---|---|
| `small` (default) | AV1 (SVT) CRF 40, preset 8 | 9.3 MB, VMAF 96.3 | ~2.4× compat | YouTube, web, modern Android/iOS/desktop players |
| `smallest` | AV1 CRF 44 | 7.2 MB, VMAF 95.2 | ~1.7× | as small as it gets while still clean |
| `compat` | H.264 CRF 23, slow | 15.8 MB, VMAF 96.0 | 1× (about real time on a 16-thread laptop) | old devices, messengers or TVs that can't play AV1 |
| `hevc` | H.265 CRF 28, medium | 10.5 MB, VMAF 93.9 | ~1.8× | players with HEVC but no AV1 (older iPhones/Macs) |

\*From `docs/encoding-benchmark.md`. Visualiser video is expensive to compress because the waveform changes every pixel column every frame.

More levers when size matters most, in order of impact:
- **Lower resolution:** `--size 720p` is less than half the pixels of 1080p. Fine for phone-first sharing.
- **CRF:** `--crf 30` with `small` (or `--crf 40` with `smallest`) is visibly softer but still clean on a waveform over a blurred background.
- **Calmer visuals:** fewer moving pixels encode smaller. In 10 s HEVC previews, `logo-pulse` came out about 15% smaller than `waveform-center`. Not benchmarked beyond that.
- **Lower `--fps`:** 24 fps saves only about 8%, because the waveform still changes every frame.

## Troubleshooting

- `avp produced no output` → rerun with `--keep-work`. avp's logs are in `<work>/cfg/audio-visualizer/log/`; `avp --verbose` style detail is in `render_*.log`.
- `unknown setting 'x'` / `'y' not one of [...]` → template typo; the message lists valid names/labels.
- Text in the wrong font → the family isn't installed. Give the font **file** in the brand kit; render.py installs it.
- Waveform barely visible → render.py must call avp through `scripts/avp_run.py` (it does); calling `avp` directly loses the `draw=full` fix.
