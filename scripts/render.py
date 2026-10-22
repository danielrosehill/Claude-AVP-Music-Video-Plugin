#!/usr/bin/env python3
"""Render an audio file to a music video with avp (audio-visualizer-python).

Pipeline:
  1. Resolve a template (JSON layer spec) against brand.json + per-render vars.
  2. Pre-process images (SVG/WebP -> PNG, fit to a pixel box, anchor placement).
  3. Compile the spec to an .avp project (avp_project.py, under avp's Python).
  4. avp renders a near-lossless intermediate, headless, in an isolated config dir.
  5. One ffmpeg pass: burn subtitles (optional) + final space-efficient encode,
     audio stream-copied from the source when the container allows it.

Stdlib only. Needs `avp`, `ffmpeg`, `ffprobe` on PATH.
Run with --help for options. Prints a JSON report on stdout at the end.
"""
import argparse
import ast
import json
import operator
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
TEMPLATE_DIRS = [os.path.join(PLUGIN_ROOT, "templates")]

# Final-encode profiles, chosen from docs/encoding-benchmark.md (30 s 1080p30
# waveform-center clip, VMAF vs the avp intermediate, ffmpeg 8.1, 2026-10-22).
PROFILES = {
    # H.264: plays everywhere. 15.8 MB / VMAF 96.0 / 1x encode time.
    "compat": ["-c:v", "libx264", "-preset", "slow", "-crf", "23",
               "-profile:v", "high", "-pix_fmt", "yuv420p"],
    # AV1: same quality as compat at 59% of the size. ~2.3x encode time.
    "small": ["-c:v", "libsvtav1", "-preset", "8", "-crf", "40", "-g", "240",
              "-pix_fmt", "yuv420p"],
    # AV1: 46% of compat, VMAF 95.2 - still clean on this kind of content.
    "smallest": ["-c:v", "libsvtav1", "-preset", "8", "-crf", "44", "-g", "240",
                 "-pix_fmt", "yuv420p"],
    # HEVC for players with HEVC but no AV1 (older Apple devices): 67% / VMAF 93.9.
    "hevc": ["-c:v", "libx265", "-preset", "medium", "-crf", "28", "-tag:v", "hvc1",
             "-pix_fmt", "yuv420p", "-x265-params", "log-level=error"],
}
CRF_FLAG = "-crf"

SIZES = {
    "1080p": (1920, 1080), "720p": (1280, 720), "4k": (3840, 2160),
    "square": (1080, 1080), "vertical": (1080, 1920), "portrait": (1080, 1350),
}

AVP_IMAGE_EXT = {".png", ".jpg", ".gif", ".bmp", ".tif", ".tiff"}
COPYABLE_AUDIO = {"mp3", "aac", "alac"}  # safe to stream-copy into MP4


def log(msg):
    print(f"[avp-render] {msg}", file=sys.stderr, flush=True)


NICE = []  # set from --nice in main(); prefixes the heavy avp/ffmpeg steps


def run(cmd, env=None, quiet=True, heavy=False):
    res = subprocess.run((NICE + cmd) if heavy else cmd, env=env,
                         capture_output=quiet, text=True)
    if res.returncode != 0:
        if quiet:
            sys.stderr.write((res.stdout or "")[-3000:] + (res.stderr or "")[-3000:])
        raise SystemExit(f"command failed ({res.returncode}): {' '.join(cmd[:4])} ...")
    return res


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
               "-of", "json", path]).stdout
    return json.loads(out)


def avp_python():
    """The interpreter avp is installed under (uv tool / pipx / venv)."""
    avp = shutil.which("avp")
    if not avp:
        raise SystemExit("avp not found on PATH - run the install-avp skill first")
    with open(os.path.realpath(avp), "rb") as f:
        first = f.readline().decode(errors="replace").strip()
    if first.startswith("#!"):
        interp = first[2:].strip().split()[0]
        if os.path.exists(interp):
            return interp
    return sys.executable


# --- template resolution -------------------------------------------------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg}


def calc(expr, names):
    """Evaluate a tiny arithmetic expression like 'H-120' or 'W*0.05'."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id in names:
            return names[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError(expr)
    return ev(ast.parse(expr, mode="eval"))


def lookup(vars_, dotted):
    cur = vars_
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return ""
        cur = cur[part]
    return "" if cur is None else cur


def substitute(obj, vars_):
    if isinstance(obj, dict):
        return {k: substitute(v, vars_) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, vars_) for v in obj]
    if isinstance(obj, str):
        whole = re.fullmatch(r"\{\{\s*([\w.]+)\s*(?:\|\s*([^}]*))?\}\}", obj)
        if whole:  # keep non-string types for whole-value placeholders
            val = lookup(vars_, whole.group(1))
            return val if val != "" else (whole.group(2) or "").strip()

        def rep(m):
            val = lookup(vars_, m.group(1))
            return str(val if val != "" else (m.group(2) or "").strip())
        return re.sub(r"\{\{\s*([\w.]+)\s*(?:\|\s*([^}]*))?\}\}", rep, obj)
    return obj


def truthy(vars_, cond):
    neg = cond.startswith("!")
    val = lookup(vars_, cond.lstrip("!"))
    return (not val) if neg else bool(val)


def to_png(src, dst_dir, box=None, cover=None, blur=0, darken=0.0):
    """Convert/resize an image to PNG avp can read.
    box=(w,h) fits inside; cover=(w,h) fills and crops; blur in px;
    darken 0..1 (avp itself has no blur/darken)."""
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    key = (src, box, cover, blur, darken)
    dst = os.path.join(dst_dir, f"{base}-{abs(hash(key)) % 10**8}.png")
    ext = os.path.splitext(src)[1].lower()
    tmp = src
    if ext == ".svg":
        tmp = os.path.join(dst_dir, base + "-svg.png")
        width = str(box[0] * 2 if box else 2000)
        if shutil.which("rsvg-convert"):
            run(["rsvg-convert", "-w", width, "-o", tmp, src])
        elif shutil.which("inkscape"):
            run(["inkscape", src, "--export-type=png", f"--export-filename={tmp}",
                 f"--export-width={width}"])
        elif shutil.which("magick"):
            run(["magick", "-background", "none", "-density", "300", src,
                 "-resize", f"{width}x", tmp])
        else:
            raise SystemExit("SVG needs rsvg-convert, inkscape or ImageMagick")
    if box is None and cover is None and not blur and not darken \
            and ext in AVP_IMAGE_EXT:
        return src
    vf = []
    if box:
        vf.append(f"scale={box[0]}:{box[1]}:force_original_aspect_ratio=decrease"
                  ":flags=lanczos")
    if cover:
        vf.append(f"scale={cover[0]}:{cover[1]}:force_original_aspect_ratio=increase"
                  f":flags=lanczos,crop={cover[0]}:{cover[1]}")
    if blur:
        vf.append(f"gblur=sigma={blur}")
    if darken:
        vf.append(f"colorchannelmixer=rr={1-darken}:gg={1-darken}:bb={1-darken}")
    vf.append("format=rgba")
    run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-frames:v", "1",
         "-vf", ",".join(vf), dst])
    return dst


FONT_DIR = os.path.expanduser("~/.local/share/fonts/avp-music-video")


def install_font(path):
    """avp's renderer resolves fonts by family through fontconfig, so a font
    file from a brand repo must be installed for the user, not just pointed at.
    Copies into ~/.local/share/fonts/avp-music-video/ and refreshes the cache."""
    dst = os.path.join(FONT_DIR, os.path.basename(path))
    if not os.path.exists(dst):
        os.makedirs(FONT_DIR, exist_ok=True)
        shutil.copy2(path, dst)
        if shutil.which("fc-cache"):
            run(["fc-cache", "-f", FONT_DIR])
        log(f"installed font {os.path.basename(path)} -> {FONT_DIR}")
    return dst


def image_size(path):
    s = probe(path)["streams"][0]
    return int(s["width"]), int(s["height"])


def anchor_xy(anchor, margin, W, H, w, h):
    v, _, hz = anchor.partition("-") if "-" in anchor else (anchor, "", anchor)
    if anchor == "center":
        return (W - w) // 2, (H - h) // 2
    x = {"left": margin, "right": W - w - margin, "center": (W - w) // 2}[hz]
    y = {"top": margin, "bottom": H - h - margin, "center": (H - h) // 2}[v]
    return x, y


NUMERIC_KEYS = {"x", "y", "xPosition", "yPosition", "fontSize", "scale", "stroke",
                "shadX", "shadY", "shadBlur", "width", "height", "opacity",
                "rotate", "sensitivity", "speed", "bars", "zoom", "hue"}


def resolve_spec(tpl, vars_, W, H, work):
    names = {"W": W, "H": H}
    layers = []
    for layer in tpl["layers"]:
        if "if" in layer and not truthy(vars_, layer["if"]):
            continue
        layer = substitute(layer, vars_)
        st = dict(layer.get("set", {}))
        for k, v in list(st.items()):
            if k in NUMERIC_KEYS and isinstance(v, str):
                st[k] = calc(v, names)
        comp = layer["component"].lower()
        if comp == "image" and st.get("image"):
            img = os.path.abspath(os.path.expanduser(st["image"]))
            if not os.path.exists(img):
                raise SystemExit(f"image not found: {img}")
            box = None
            if "fit" in layer:
                fw, fh = layer["fit"]
                box = (int(calc(str(fw), names)), int(calc(str(fh), names)))
            cover = (W, H) if layer.get("cover") else None
            img = to_png(img, os.path.join(work, "img"), box, cover,
                         float(layer.get("blur", 0)), float(layer.get("darken", 0)))
            st["image"] = img
            if box or cover:
                st.setdefault("scale", 100)
            if "anchor" in layer:
                w, h = image_size(img)
                margin = int(calc(str(layer.get("margin", 0)), names))
                st["x"], st["y"] = anchor_xy(layer["anchor"], margin, W, H, w, h)
        if comp == "video" and st.get("video"):
            st["video"] = os.path.abspath(os.path.expanduser(st["video"]))
        if comp == "text" and st.get("font") and os.path.isfile(str(st["font"])):
            st["font"] = install_font(os.path.abspath(st["font"]))
        layers.append({"component": layer["component"], "set": st})
    return layers


def find_template(name):
    if os.path.isfile(name):
        return name
    for d in TEMPLATE_DIRS:
        p = os.path.join(d, name if name.endswith(".json") else name + ".json")
        if os.path.isfile(p):
            return p
    avail = sorted(f[:-5] for d in TEMPLATE_DIRS if os.path.isdir(d)
                   for f in os.listdir(d) if f.endswith(".json"))
    raise SystemExit(f"template '{name}' not found. Available: {avail}")


def load_brand(path):
    if not path:
        for cand in ("avp-brand.json", "brand/avp-brand.json", ".avp/brand.json"):
            if os.path.isfile(cand):
                path = cand
                break
    if not path:
        return {}, None
    path = os.path.abspath(path)
    with open(path) as f:
        brand = json.load(f)
    base = os.path.dirname(path)

    def absify(v):
        if isinstance(v, str) and v and not v.startswith("#") and (
                "/" in v or "." in os.path.basename(v)):
            p = os.path.normpath(os.path.join(base, os.path.expanduser(v)))
            return p if os.path.exists(p) else v
        if isinstance(v, dict):
            return {k: absify(x) for k, x in v.items()}
        return v
    return {k: absify(v) if k != "colors" else v for k, v in brand.items()}, path


# --- main ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("-o", "--output", help="default: <audio>.<template>.mp4 next to audio")
    ap.add_argument("-t", "--template", default=None,
                    help="template name (templates/) or path; default brand.default_template or waveform-center")
    ap.add_argument("-b", "--brand", help="brand manifest (default: ./avp-brand.json)")
    ap.add_argument("--title"), ap.add_argument("--artist")
    ap.add_argument("--subtitle", help="second text line (album, episode, URL)")
    ap.add_argument("--cover", help="cover art image (default: embedded art in the audio)")
    ap.add_argument("--background", help="background image/video, overrides brand")
    ap.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--size", help="WxH or one of " + ", ".join(SIZES))
    ap.add_argument("--fps", type=int)
    ap.add_argument("--subs", help="lyrics/subtitles to burn in (.ass/.srt/.lrc)")
    ap.add_argument("--subs-style", default="{}",
                    help="JSON overrides for lyrics_to_ass styling (font, size, colors...)")
    ap.add_argument("--karaoke", action="store_true",
                    help="karaoke sweep highlight when converting .lrc/.srt")
    ap.add_argument("-p", "--profile", default="small", choices=sorted(PROFILES))
    ap.add_argument("--crf", type=int, help="override the profile's CRF")
    ap.add_argument("--reencode-audio", action="store_true",
                    help="always encode AAC instead of stream-copying source audio")
    ap.add_argument("--preview", type=float, metavar="SECONDS",
                    help="render only a clip of this length (fast look)")
    ap.add_argument("--start", type=float, default=None,
                    help="preview start (s); default 1/3 into the track")
    ap.add_argument("--nice", type=int, default=10,
                    help="CPU niceness for avp and the encode (0 = normal priority)")
    ap.add_argument("--threads", type=int,
                    help="cap encoder threads (default: ffmpeg decides, i.e. all cores)")
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve template and print the layer spec only")
    a = ap.parse_args()

    t0 = time.time()
    if a.nice and shutil.which("nice"):
        NICE[:] = ["nice", "-n", str(a.nice)]
    audio = os.path.abspath(a.audio)
    info = probe(audio)
    astream = next(s for s in info["streams"] if s["codec_type"] == "audio")
    tags = {k.lower(): v for k, v in info["format"].get("tags", {}).items()}
    duration = float(info["format"]["duration"])

    brand, brand_path = load_brand(a.brand)
    tpl_path = find_template(a.template or brand.get("default_template") or "waveform-center")
    with open(tpl_path) as f:
        tpl = json.load(f)
    tname = os.path.splitext(os.path.basename(tpl_path))[0]

    out = tpl.get("output", {})
    W, H = out.get("width", 1920), out.get("height", 1080)
    if a.size:
        W, H = SIZES.get(a.size) or tuple(int(v) for v in a.size.lower().split("x"))
    fps = a.fps or out.get("fps", 30)

    work = tempfile.mkdtemp(prefix="avp-render-")
    try:
        # cover art: explicit, else embedded picture stream
        cover = a.cover
        if not cover and any(s.get("disposition", {}).get("attached_pic")
                             for s in info["streams"]):
            cover = os.path.join(work, "cover.png")
            run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-an",
                 "-frames:v", "1", cover])
        vars_ = {
            "title": a.title or tags.get("title") or
            os.path.splitext(os.path.basename(audio))[0],
            "artist": a.artist or tags.get("artist") or brand.get("name", ""),
            "subtitle": a.subtitle or "",
            "cover": os.path.abspath(cover) if cover else "",
            "brand": brand,
            "W": W, "H": H,
        }
        vars_["background"] = (os.path.abspath(a.background) if a.background
                               else brand.get("background") or vars_["cover"])
        bg = vars_["background"]
        is_video = os.path.splitext(bg)[1].lower() in (".mp4", ".mov", ".mkv", ".webm")
        vars_["background_video"] = bg if bg and is_video else ""
        vars_["background_image"] = bg if bg and not is_video else ""
        for kv in a.var:
            k, _, v = kv.partition("=")
            vars_[k] = v

        layers = resolve_spec(tpl, vars_, W, H, work)
        spec = {"output": {"width": W, "height": H, "fps": fps}, "layers": layers}
        if a.dry_run:
            print(json.dumps(spec, indent=2))
            return

        # audio clip for previews
        src_audio, offset = audio, 0.0
        if a.preview:
            offset = a.start if a.start is not None else max(0.0, duration / 3)
            src_audio = os.path.join(work, "clip" + os.path.splitext(audio)[1])
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(offset), "-t", str(a.preview),
                 "-i", audio, "-map", "0:a", "-c", "copy", src_audio])

        spec_path = os.path.join(work, "spec.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f, indent=2)
        cfg = os.path.join(work, "cfg")
        proj = os.path.join(work, "project.avp")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=cfg)
        log(f"template {tname} @ {W}x{H} {fps}fps, {len(layers)} layers")
        run([avp_python(), "-I", os.path.join(HERE, "avp_project.py"), spec_path,
             proj, os.path.join(cfg, "audio-visualizer")], env=env)

        inter = os.path.join(work, "intermediate.mp4")
        log("avp rendering (roughly real-time at 1080p)...")
        t1 = time.time()
        run([avp_python(), "-I", os.path.join(HERE, "avp_run.py"), proj,
             "-i", src_audio, "-o", inter], env=env, heavy=True)
        if not os.path.exists(inter) or os.path.getsize(inter) < 1000:
            raise SystemExit("avp produced no output - rerun with --keep-work and "
                             "check the log in <work>/cfg/audio-visualizer/log")
        t_avp = time.time() - t1

        # final pass
        output = a.output or os.path.join(
            os.path.dirname(audio),
            f"{os.path.splitext(os.path.basename(audio))[0]}.{tname}"
            f"{'.preview' if a.preview else ''}.mp4")
        vf = []
        if a.subs:
            subs = os.path.abspath(a.subs)
            # template "lyrics" block gives placement defaults; --subs-style wins
            style = {k: (calc(v, {"W": W, "H": H}) if k in ("size", "margin_v")
                         and isinstance(v, str) else v)
                     for k, v in substitute(tpl.get("lyrics", {}), vars_).items()}
            style.update(json.loads(a.subs_style))
            if brand.get("font", {}).get("file"):
                style.setdefault("fontfile", brand["font"]["file"])
            if brand.get("colors"):
                style.setdefault("brand_colors", brand["colors"])
            ass = os.path.join(work, "subs.ass")
            cmd = [sys.executable, "-I", os.path.join(HERE, "lyrics_to_ass.py"), subs, ass,
                   "--width", str(W), "--height", str(H), "--style", json.dumps(style)]
            if a.karaoke:
                cmd.append("--karaoke")
            if offset:
                cmd += ["--shift", str(-offset)]
            run(cmd)
            fontsdir = os.path.dirname(style["fontfile"]) if style.get("fontfile") else None
            esc = ass.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            vf.append(f"subtitles='{esc}'" + (f":fontsdir='{fontsdir}'" if fontsdir else ""))

        profile = a.profile
        encoders = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
        if PROFILES[profile][1] not in encoders:
            log(f"ffmpeg lacks {PROFILES[profile][1]}; falling back to profile compat")
            profile = "compat"
        vcodec = list(PROFILES[profile])
        if a.crf is not None:
            vcodec[vcodec.index(CRF_FLAG) + 1] = str(a.crf)
        copy_audio = (astream["codec_name"] in COPYABLE_AUDIO and not a.reencode_audio)
        acodec = ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]
        cmd = ["ffmpeg", "-v", "error", "-stats", "-y", "-i", inter, "-i", src_audio,
               "-map", "0:v:0", "-map", "1:a:0"]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        if a.threads:
            vcodec += ["-threads", str(a.threads)]
            if "libsvtav1" in vcodec:
                vcodec += ["-svtav1-params", f"lp={a.threads}"]
        cmd += vcodec + acodec + ["-r", str(fps), "-shortest",
                                  "-movflags", "+faststart", output]
        log(f"final encode: profile={profile} audio={'copy' if copy_audio else 'aac'}")
        t2 = time.time()
        run(cmd, heavy=True)
        t_enc = time.time() - t2

        fin = probe(output)
        report = {
            "output": output,
            "template": tname,
            "brand": brand_path,
            "size": f"{W}x{H}", "fps": fps,
            "profile": profile,
            "video_codec": next(s["codec_name"] for s in fin["streams"]
                                if s["codec_type"] == "video"),
            "audio": "copied " + astream["codec_name"] if copy_audio else "aac 192k",
            "duration_s": round(float(fin["format"]["duration"]), 2),
            "bytes": int(fin["format"]["size"]),
            "mb": round(int(fin["format"]["size"]) / 1e6, 2),
            "kbps_total": round(int(fin["format"]["bit_rate"]) / 1000),
            "subtitles": bool(a.subs),
            "timing_s": {"avp": round(t_avp, 1), "encode": round(t_enc, 1),
                         "total": round(time.time() - t0, 1)},
        }
        if a.keep_work:
            report["work_dir"] = work
        print(json.dumps(report, indent=2))
    finally:
        if not a.keep_work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
