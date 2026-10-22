# Encoding benchmark: choosing the final-encode profiles

Measured 2026-10-22. Source: a 30 s, 1920×1080, 30 fps avp render of the
`waveform-center` template (blurred cover-art background, full-frame white
waveform at opacity 75 — the shipped default is now 60, logo, title). This is the 16 Mbps `veryfast` H.264 intermediate that
`render.py` produces before the final encode. Audio excluded (the plugin
stream-copies it, so it's identical across profiles).

Quality is VMAF (libvmaf, default model) and SSIM of each encode against that
intermediate, with ffmpeg 8.1 (BtbN static GPL build) on a Modal 16-CPU box.
Lower-resolution and lower-fps rows are scaled/converted back to 1080p30 before
scoring, so they include the cost of upscaling.

| Encode | MB / 30 s | Mbps | VMAF | SSIM |
|---|---|---|---|---|
| x264 slow CRF 23 (**compat**) | 15.76 | 4.20 | 95.97 | 0.9890 |
| x264 slow CRF 26 | 11.39 | 3.04 | 93.21 | 0.9839 |
| x264 medium CRF 23 | 16.19 | 4.32 | 95.88 | 0.9889 |
| x265 slow CRF 26 | 13.74 | 3.66 | 96.41 | 0.9874 |
| x265 medium CRF 26 | 13.10 | 3.49 | 95.34 | 0.9854 |
| x265 medium CRF 28 (**hevc**) | 10.55 | 2.81 | 93.92 | 0.9817 |
| SVT-AV1 p6 CRF 36 | 12.01 | 3.20 | 97.39 | 0.9907 |
| SVT-AV1 p8 CRF 36 | 12.25 | 3.27 | 97.07 | 0.9890 |
| SVT-AV1 p8 CRF 40 (**small**, default) | 9.31 | 2.48 | 96.27 | 0.9868 |
| SVT-AV1 p8 CRF 44 (**smallest**) | 7.22 | 1.93 | 95.19 | 0.9839 |
| SVT-AV1 p10 CRF 38 | 13.13 | 3.50 | 94.83 | 0.9819 |
| x264 slow CRF 23, 24 fps | 14.47 | 3.86 | 93.79 | 0.9835 |
| SVT-AV1 p8 CRF 38, 24 fps | 9.06 | 2.42 | 94.11 | 0.9819 |
| x264 slow CRF 23, 720p | 8.48 | 2.26 | 84.17 | 0.9454 |
| SVT-AV1 p8 CRF 36, 720p | 7.15 | 1.91 | 85.11 | 0.9456 |

Encode time for the same 30 s clip (Modal, 16 CPUs; `-threads 8` was within noise
of 16). Ratios carry over to other machines better than absolute seconds. On the
author's 16-thread laptop, x264 slow took 29 s and x265 slow 178 s.

| Encode | seconds | × x264 slow |
|---|---|---|
| x264 slow CRF 23 | 9.5 | 1.0 |
| x265 slow CRF 26 | 38.6 | 4.1 |
| x265 medium CRF 28 | 16.8 | 1.8 |
| SVT-AV1 p6 CRF 36 | 14.3 | 1.5 |
| SVT-AV1 p8 CRF 40 | 22.6 | 2.4 |
| SVT-AV1 p8 CRF 44 | 16.3 | 1.7 |

SVT-AV1 timings varied run to run (p8 came out slower than p6 here). Treat AV1 as
"roughly 1.5–2.5× x264 slow".

## Conclusions

- **AV1 is the default.** CRF 40 matches x264 CRF 23's quality (VMAF 96.3 vs 96.0)
  at 59% of the size, for ~2× the encode time. CRF 44 is 46% of the size at VMAF 95.2.
- **x265 slow isn't worth it.** Barely smaller than x264 at 4× the time. HEVC stays
  only as an option (`hevc`, medium preset) for players with HEVC but no AV1 decoding.
- **24 fps saves ~8%.** The scrolling waveform still changes every frame. It's a
  small lever, and the VMAF drop above is partly the fps conversion in scoring.
- **720p roughly halves the size** but scores much lower once upscaled to 1080p. It
  makes sense only when the video will be watched small (phones, messengers).
- Visualiser video is expensive: ~2–4 Mbps for 1080p, versus well under 1 Mbps for a
  static image + audio. Templates with less full-frame motion compress better; in
  10 s previews `logo-pulse` was ~15% smaller than `waveform-center`.
- **Hardware encoding** (AMD VAAPI on the author's laptop) encoded 10 s in 1.8 s but
  was 6–7 Mbps at QP 26, worse than software H.264 at CRF 23. Not used.

## Reproduce

Render with `--keep-work`, then encode `<work>/intermediate.mp4` with each setting and
score:

```bash
ffmpeg -i out.mp4 -i intermediate.mp4 -lavfi "[0:v]scale=1920:1080,fps=30[d];[d][1:v]libvmaf" -f null -
```

Ubuntu's ffmpeg has no libvmaf; the BtbN static builds do. The heavy runs here were
done on Modal (CPU only, no GPU needed) to keep the laptop free.
