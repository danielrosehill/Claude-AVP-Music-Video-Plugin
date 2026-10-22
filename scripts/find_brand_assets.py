#!/usr/bin/env python3
"""Scan a repository for brand assets and print ranked candidates as JSON.

  find_brand_assets.py [ROOT] [--max N]

Finds:
  manifests  existing avp-brand.json / brand.json / *brand*.{json,yaml,yml,toml}
  logos      images whose path says logo / brand / wordmark / mark / icon / favicon
  backgrounds images whose path says background / bg / hero / banner / cover / og
  fonts      .ttf / .otf files (woff/woff2 listed separately: libass and Qt
             need ttf/otf, so a woff2-only brand font must be converted first)
  colors     hex colours from CSS custom properties, Tailwind/theme configs and
             brand files, with the variable name they were declared under
It ranks; it does not decide. The calling skill picks and writes avp-brand.json.
Stdlib only.
"""
import argparse
import json
import os
import re
import struct
from collections import Counter, defaultdict

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", ".nuxt", "out",
             "vendor", ".venv", "venv", "__pycache__", ".cache", "coverage",
             "target", ".turbo", ".vercel", ".astro", "site-packages"}
IMG_EXT = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".ico"}
FONT_EXT = {".ttf", ".otf"}
WEBFONT_EXT = {".woff", ".woff2"}
COLOR_FILES = re.compile(
    r"(\.css|\.scss|\.sass|\.less|tailwind\.config\.\w+|theme\.\w+|"
    r"brand[^/]*\.(json|ya?ml|toml)|tokens?[^/]*\.json|colors?\.\w+)$", re.I)
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
CSS_VAR = re.compile(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\b")
KEY_VAL = re.compile(r"""["']?([\w-]+)["']?\s*[:=]\s*["'](#[0-9a-fA-F]{3,6})["']""")
MANIFEST = re.compile(
    r"^(avp-brand|brand|branding|brand[-_]kit|brand[-_]tokens|design[-_]tokens)"
    r"\.(json|ya?ml|toml)$")
CSS_KEYWORDS = {"inherit", "initial", "unset", "revert", "sans-serif", "serif",
                "monospace", "system-ui", "cursive", "fantasy"}
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;]+);", re.I)

LOGO_WORDS = {"logo": 5, "wordmark": 5, "logotype": 5, "brand": 3, "mark": 2,
              "icon": 1, "favicon": 1, "emblem": 3, "monogram": 3}
BG_WORDS = {"background": 4, "bg": 3, "hero": 3, "banner": 3, "cover": 3,
            "og": 2, "social": 2, "wallpaper": 4, "backdrop": 4, "splash": 2}
DIR_BONUS = {"brand": 3, "branding": 3, "logos": 3, "logo": 3, "assets": 1,
             "public": 1, "static": 1, "images": 1, "img": 1, "media": 1,
             "press": 2, "press-kit": 3, "presskit": 3}
NAME_HINTS = {"primary": 5, "brand": 5, "accent": 4, "secondary": 4,
              "background": 2, "bg": 2, "foreground": 2, "text": 1}


def words(path):
    return re.split(r"[^a-z0-9]+", path.lower())


def score(path, table):
    ws = words(path)
    s = sum(v for w, v in table.items() if w in ws or any(x.startswith(w) for x in ws))
    s += sum(v for d, v in DIR_BONUS.items() if d in ws[:-1])
    return s


def img_dims(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if path.lower().endswith(".svg"):
            vb = re.search(rb'viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"', head)
            if vb:
                return int(float(vb.group(1))), int(float(vb.group(2)))
    except OSError:
        pass
    return None


def font_name(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        num = struct.unpack(">H", data[4:6])[0]
        for i in range(num):
            tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            if tag != b"name":
                continue
            _, count, strings = struct.unpack(">HHH", data[off:off + 6])
            names = {}
            for j in range(count):
                pid, _, lid, nid, ln, so = struct.unpack(
                    ">HHHHHH", data[off + 6 + 12 * j:off + 18 + 12 * j])
                if nid in (1, 2) and pid == 3:
                    raw = data[off + strings + so:off + strings + so + ln]
                    names[nid] = raw.decode("utf-16-be", "ignore")
            return names.get(1), names.get(2)
    except (OSError, struct.error):
        pass
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    manifests, logos, bgs, fonts, webfonts = [], [], [], [], []
    named = defaultdict(Counter)   # colour -> Counter(var names)
    freq = Counter()
    families = Counter()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")
                  or d in (".avp", ".brand")]
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            ext = os.path.splitext(fn)[1].lower()
            low = fn.lower()
            if MANIFEST.match(low):
                manifests.append(rel)
            if ext in IMG_EXT:
                size = os.path.getsize(p)
                dims = img_dims(p)
                ls, bs = score(rel, LOGO_WORDS), score(rel, BG_WORDS)
                entry = {"path": rel, "bytes": size, "dims": dims}
                if ls >= 3:
                    entry["score"] = ls + (2 if ext == ".svg" else 0)
                    logos.append(entry)
                if bs >= 3 and size > 30_000:
                    bgs.append(dict(entry, score=bs))
            elif ext in FONT_EXT:
                fam, sub = font_name(p)
                fonts.append({"path": rel, "family": fam, "style": sub})
            elif ext in WEBFONT_EXT:
                webfonts.append(rel)
            if COLOR_FILES.search(fn) and os.path.getsize(p) < 2_000_000:
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for var, col in CSS_VAR.findall(txt) + KEY_VAL.findall(txt):
                    named[col.lower()][var] += 1
                for col in HEX.findall(txt):
                    freq[col.lower()] += 1
                for fam in FONT_FAMILY.findall(txt):
                    first = fam.split(",")[0].strip().strip("'\"")
                    if first and not first.startswith("var(") \
                            and first.lower() not in CSS_KEYWORDS:
                        families[first] += 1

    def cscore(col):
        names = named.get(col, {})
        hint = max((v for n in names for k, v in NAME_HINTS.items() if k in n.lower()),
                   default=0)
        return hint * 10 + min(freq[col], 20)

    colors = sorted(set(freq) | set(named), key=cscore, reverse=True)
    out = {
        "root": root,
        "manifests": manifests,
        "logos": sorted(logos, key=lambda e: -e["score"])[:a.max],
        "backgrounds": sorted(bgs, key=lambda e: -e["score"])[:a.max],
        "fonts": fonts[:a.max * 2],
        "webfonts_need_conversion": webfonts[:a.max],
        "css_font_families": [f for f, _ in families.most_common(a.max)],
        "colors": [{"hex": c, "uses": freq[c],
                    "names": [n for n, _ in named.get(c, Counter()).most_common(4)]}
                   for c in colors[:a.max * 2]],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
