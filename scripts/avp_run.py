#!/usr/bin/env python3
"""Run the avp CLI with render fixes applied. Same arguments as `avp`.

Must run under avp's own interpreter (render.py does this).

Patch: Waveform (Cline/Line modes) uses ffmpeg `showwaves` with its default
draw=scale, which divides each sample's intensity across the samples drawn in
a column. At 30 fps / 44.1 kHz that is barely visible at 1280 px wide and
nearly invisible at 1920 px (measured 2026-10-22, avp 2.2.4, ffmpeg 8.0:
mean alpha 56 at 720p vs 16 at 1080p; draw=full gives 91 / 84).
Remove once avp sets draw=full itself or exposes the option.
"""
import sys

from avp.components import waveform


_orig = waveform.Component.makeFfmpegFilter


def _patched(self, *args, **kwargs):
    out = _orig(self, *args, **kwargs)
    return [
        a.replace(":scale=", ":draw=full:scale=", 1) if "showwaves=" in a else a
        for a in out
    ]


waveform.Component.makeFfmpegFilter = _patched

if __name__ == "__main__":
    from avp.cli import main

    sys.argv[0] = "avp"
    sys.exit(main())
