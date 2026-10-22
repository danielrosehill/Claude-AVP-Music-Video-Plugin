---
name: karaoke-lyrics
description: Prepare timed lyrics for a music video and burn them in — karaoke-style sweep highlight or plain line-by-line subtitles — from an LRC, enhanced (word-timed) LRC, SRT or ASS file, or from plain lyrics text by aligning it to the song. Use when the user says "add the lyrics", "karaoke video", "burn in subtitles", "lyrics video", "sync these lyrics to the song", or hands over a Suno song with its lyrics.
---

# Karaoke / lyrics subtitles

Lyrics are burned in during the final encode of `render-music-video` (one ffmpeg pass: subtitles + compression), so there is never an extra generation of video quality loss. This skill gets the lyrics into a timed format and picks the options.

Script location: see `install-avp` ("Script location").

## 1. Get timed lyrics — best source first

| What the user has | Do |
|---|---|
| `.ass` | use as-is (styling is theirs; only time-shifted for previews) |
| enhanced `.lrc` (`[00:12.00] <00:12.00> word <00:12.40> word …`) | exact per-word karaoke |
| `.lrc` (`[mm:ss.xx] line`) | line timing; `--karaoke` sweeps each line evenly — approximate but usually fine for sung lines |
| `.srt` / `.vtt` | convert VTT → SRT with `ffmpeg -i in.vtt out.srt`; then as SRT |
| plain lyrics text (e.g. copied from Suno) | align it — step 2 |
| nothing | transcribe the vocal — step 2 without the text, then correct the words against what the user says the lyrics are |

## 2. Aligning plain lyrics to the audio

Lyrics need timestamps; text alone has none. Use a local word-timestamp ASR on the song (better: on an isolated vocal stem — Demucs `--two-stems vocals` — when the mix is dense):

```bash
# faster-whisper / whisper both emit word timings
whisper song.mp3 --model medium --word_timestamps True --output_format json -o work/
```

Then build an enhanced LRC: walk the user's lyric lines in order, match each line's words to the ASR word stream (fuzzy — sung words are often misheard), and take each word's start time. Write lines as `[mm:ss.xx] <mm:ss.xx> word <mm:ss.xx> word …`. Lines the ASR missed entirely: interpolate between neighbours and tell the user which ones. Section headers like `[Chorus]` / `[Verse 2]` from Suno are not sung — drop them.

Show the user the first few timed lines before rendering a full video. A 10-second preview render around the chorus is the cheapest check.

## 3. Render

```bash
python3 "$ROOT/scripts/render.py" song.mp3 -t waveform-center \
  --subs lyrics.lrc --karaoke --preview 15 --start 60     # check timing/placement
python3 "$ROOT/scripts/render.py" song.mp3 -t waveform-center \
  --subs lyrics.lrc --karaoke                                 # full render
```

`--preview` shifts the lyric times automatically, so previews from any `--start` stay in sync.

Styling comes from, in order: the template's `"lyrics"` block (placement that avoids its title/logo), `avp-brand.json` (font file, `colors.text` for unsung, `colors.primary` for the sweep), then `--subs-style` JSON overrides:

```bash
--subs-style '{"position":"middle","size":72,"highlight":"#00e0ff","outline":"#000000","outline_px":5}'
```

Keys: `font`, `fontfile`, `size`, `color`, `highlight`, `outline`, `outline_px`, `shadow_px`, `position` (`bottom|middle|top`), `margin_v`, `bold`. Without `--karaoke`, lines appear plainly in `color`.

To convert without rendering (e.g. to hand-edit the ASS):

```bash
python3 -I "$ROOT/scripts/lyrics_to_ass.py" lyrics.lrc lyrics.ass --width 1920 --height 1080 --karaoke
```

## Notes
- Burned-in subtitles can't be turned off. If the user also wants selectable captions on YouTube, upload the `.srt` alongside the video.
- Hebrew/Arabic lyrics: libass handles RTL shaping; use a font that covers the script (set `font`/`fontfile`), and check a preview frame.
- A line stays up until the next line starts, capped at 8 s, so instrumental breaks don't hold a stale line.
