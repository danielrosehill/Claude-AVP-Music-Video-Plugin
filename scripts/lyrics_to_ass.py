#!/usr/bin/env python3
"""Convert lyrics (.lrc / enhanced .lrc / .srt / .ass) to a styled ASS file for
burning into a music video with ffmpeg's `subtitles` filter.

  lyrics_to_ass.py IN OUT --width 1920 --height 1080 [--karaoke] [--shift S]
                   [--style '{"font":"Inter","size":64,...}']

Style keys (all optional):
  font         font family name (must be installed, or in fontsdir)
  fontfile     path to a .ttf/.otf; its family name is read from the file
  size         px at the output resolution (default H/15)
  color        unsung / normal text colour   (default brand text or #FFFFFF)
  highlight    sung colour for --karaoke     (default brand primary or #FFCC00)
  outline      outline colour (default #000000), outline_px (default size/16)
  shadow_px    default 0
  position     bottom | middle | top        (default bottom)
  margin_v     px from the edge              (default H/12)
  bold         true/false (default true)
  brand_colors dict from avp-brand.json (render.py passes it)

Timing:
  .lrc lines       [mm:ss.xx] text   -> each line shown until the next starts
  enhanced .lrc    [mm:ss.xx] <mm:ss.xx> word <mm:ss.xx> word ...  -> exact
                   per-word karaoke (\\kf) when --karaoke is set
  .srt             start/end per cue; --karaoke spreads the cue time across
                   words evenly (approximate sweep)
  .ass             passed through (only --shift is applied)
Stdlib only.
"""
import argparse
import json
import re
import struct
import sys

LRC_TAG = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
LRC_WORD = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")
SRT_TIME = re.compile(
    r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
MAX_LINE_S = 8.0  # cap how long a final/isolated .lrc line stays on screen


def ass_color(hexstr, alpha=0):
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def font_family(path):
    """Read the family name (nameID 1) from a TTF/OTF name table."""
    with open(path, "rb") as f:
        data = f.read()
    num = struct.unpack(">H", data[4:6])[0]
    for i in range(num):
        tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        if tag != b"name":
            continue
        _, count, strings = struct.unpack(">HHH", data[off:off + 6])
        best = None
        for j in range(count):
            pid, eid, lid, nid, ln, so = struct.unpack(
                ">HHHHHH", data[off + 6 + 12 * j: off + 18 + 12 * j])
            if nid != 1:
                continue
            raw = data[off + strings + so: off + strings + so + ln]
            name = raw.decode("utf-16-be" if pid in (0, 3) else "latin-1", "ignore")
            if pid == 3 and lid == 0x409:
                return name
            best = best or name
        return best
    return None


def parse_lrc(text):
    lines = []
    for raw in text.splitlines():
        stamps = LRC_TAG.findall(raw)
        body = LRC_TAG.sub("", raw).strip()
        if not stamps or re.match(r"^[a-z]+:", body, re.I) and not LRC_WORD.search(body):
            continue  # metadata tags like [ar:...] have no time stamps
        words = None
        if LRC_WORD.search(body):
            parts = LRC_WORD.split(body)  # text, m, s, text, m, s, text...
            words = []
            for k in range(1, len(parts) - 2, 3):
                t = int(parts[k]) * 60 + float(parts[k + 1])
                w = parts[k + 2]
                if w.strip():
                    words.append((t, w))
            body = "".join(w for _, w in words).strip()
        for m, s in stamps:
            lines.append({"start": int(m) * 60 + float(s), "text": body, "words": words})
    lines.sort(key=lambda x: x["start"])
    for i, ln in enumerate(lines):
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else ln["start"] + MAX_LINE_S
        ln["end"] = min(nxt, ln["start"] + MAX_LINE_S)
    return [ln for ln in lines if ln["text"]]


def parse_srt(text):
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        m = SRT_TIME.search(block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = block[m.end():].strip()
        body = re.sub(r"<[^>]+>", "", body).replace("\n", "\\N")
        if body:
            cues.append({"start": start, "end": end, "text": body, "words": None})
    return cues


def karaoke_text(ln):
    """Build {\\kf} tagged text. Exact if word times exist, else even spread."""
    if ln["words"]:
        out, words = [], ln["words"]
        for i, (t, w) in enumerate(words):
            nxt = words[i + 1][0] if i + 1 < len(words) else ln["end"]
            if i == 0 and t > ln["start"]:
                out.append(f"{{\\k{int(round((t - ln['start']) * 100))}}}")
            out.append(f"{{\\kf{max(1, int(round((nxt - t) * 100)))}}}{w}")
        return "".join(out)
    tokens = re.findall(r"\\N|(?:(?!\\N)\S)+\s*", ln["text"])
    chars = sum(len(t) for t in tokens if t != "\\N") or 1
    dur = (ln["end"] - ln["start"]) * 0.9  # finish the sweep slightly early
    return "".join(t if t == "\\N" else
                   f"{{\\kf{max(1, int(round(dur * 100 * len(t) / chars)))}}}{t}"
                   for t in tokens)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"), ap.add_argument("dst")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--style", default="{}")
    ap.add_argument("--karaoke", action="store_true")
    ap.add_argument("--shift", type=float, default=0.0, help="add S seconds to all times")
    a = ap.parse_args()
    st = json.loads(a.style)
    W, H = a.width, a.height

    text = open(a.src, encoding="utf-8-sig").read()
    ext = a.src.lower().rsplit(".", 1)[-1]
    if ext == "ass":
        if a.shift:
            def mv(m):
                parts = m.group(0).split(",")
                for i in (1, 2):
                    hh, mm, ss = parts[i].split(":")
                    parts[i] = ass_time(int(hh) * 3600 + int(mm) * 60 + float(ss) + a.shift)
                return ",".join(parts)
            text = re.sub(r"^Dialogue:[^,]*,[^,]*,[^,]*", mv, text, flags=re.M)
        open(a.dst, "w", encoding="utf-8").write(text)
        return
    cues = parse_lrc(text) if ext == "lrc" else parse_srt(text)
    if not cues:
        sys.exit(f"no timed lines found in {a.src}")

    bc = st.get("brand_colors", {})
    font = st.get("font")
    if not font and st.get("fontfile"):
        font = font_family(st["fontfile"])
    font = font or "DejaVu Sans"
    size = int(st.get("size", H / 15))
    color = st.get("color", bc.get("text", "#FFFFFF"))
    hl = st.get("highlight", bc.get("primary", "#FFCC00"))
    outline = st.get("outline", "#000000")
    align = {"bottom": 2, "middle": 5, "top": 8}[st.get("position", "bottom")]
    margin_v = int(st.get("margin_v", H / 12))
    bold = -1 if st.get("bold", True) else 0
    outline_px = st.get("outline_px", max(2, size // 16))
    shadow_px = st.get("shadow_px", 0)
    # In ASS karaoke, Primary = sung (after sweep), Secondary = not yet sung.
    primary, secondary = (hl, color) if a.karaoke else (color, color)

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyrics,{font},{size},{ass_color(primary)},{ass_color(secondary)},{ass_color(outline)},{ass_color("#000000", 0x80)},{bold},0,0,0,100,100,0,0,1,{outline_px},{shadow_px},{align},{W // 16},{W // 16},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for ln in cues:
        start, end = ln["start"] + a.shift, ln["end"] + a.shift
        if end <= 0:
            continue
        body = karaoke_text(ln) if a.karaoke else ln["text"]
        rows.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Lyrics,,0,0,0,,{body}")
    with open(a.dst, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(rows) + "\n")
    print(f"{len(rows)} lines -> {a.dst} (font {font}, {size}px)", file=sys.stderr)


if __name__ == "__main__":
    main()
