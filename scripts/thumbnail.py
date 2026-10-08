#!/usr/bin/env python3
"""Pick thumbnail frames and compose a 1280x720 YouTube thumbnail.

Usage:
  thumbnail.py candidates VIDEO OUTDIR [--count 12]
      Saves OUTDIR/cand_XX_<time>.jpg (sharpest/most representative frame in each slice
      of the video) plus OUTDIR/contact_sheet.jpg, a numbered grid you can look at to choose.

  thumbnail.py make SOURCE OUTPUT.jpg [--at 1:23] [--text "BIG WORDS"] [--position left|right|center|top|bottom]
                    [--color yellow] [--font PATH] [--size 0.16] [--zoom 1.0]
      SOURCE is an image or a video (use --at to choose the frame). The frame is cropped to
      16:9, scaled to 1280x720, optionally zoomed, given a subtle contrast/saturation punch, and
      the text is drawn with a thick outline. Result is a JPEG under YouTube's 2 MB limit.

Good thumbnails: a clear face/emotion or subject, 2-5 words max, high contrast, readable
at phone size. Avoid the bottom-right corner (the duration badge covers it).
"""
import argparse
import os
import shutil
import tempfile

from _common import default_font, duration, fmt_ts, parse_ts, require, run


def candidates(args):
    os.makedirs(args.outdir, exist_ok=True)
    total = duration(args.video)
    n = max(1, args.count)
    paths = []
    for i in range(n):
        t = total * (i + 0.5) / n
        out = os.path.join(args.outdir, f"cand_{i + 1:02d}_{fmt_ts(t).replace(':', '-')}.jpg")
        # thumbnail filter picks the most representative of the next ~60 frames
        run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", args.video, "-vf",
             "thumbnail=60,scale=1280:-2", "-frames:v", "1", "-q:v", "2", out])
        paths.append((out, t))
    cols = 4
    rows = (n + cols - 1) // cols
    labeled = []
    tmp = tempfile.mkdtemp()
    font = default_font()
    try:
        for i, (p, t) in enumerate(paths):
            lp = os.path.join(tmp, f"l{i:03d}.jpg")
            txt = f"{i + 1}  {fmt_ts(t)}".replace(":", "\\:")
            ff = f"fontfile={font}:" if font else ""
            run(["ffmpeg", "-y", "-i", p, "-vf",
                 f"scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,"
                 f"drawtext={ff}text='{txt}':x=10:y=10:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6",
                 "-q:v", "3", lp])
            labeled.append(lp)
        for j in range(len(labeled), rows * cols):  # pad grid with black tiles
            bp = os.path.join(tmp, f"l{j:03d}.jpg")
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=480x270", "-frames:v", "1", bp])
        sheet = os.path.join(args.outdir, "contact_sheet.jpg")
        run(["ffmpeg", "-y", "-framerate", "1", "-i", os.path.join(tmp, "l%03d.jpg"), "-vf",
             f"tile={cols}x{rows}:padding=4", "-frames:v", "1", "-q:v", "3", sheet])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {n} candidates and {sheet}")


def make(args):
    font = args.font or default_font()
    if args.text and not font:
        raise SystemExit("error: no font found; pass --font /path/to/font.ttf")
    src = ["-i", args.source]
    if args.at is not None:
        src = ["-ss", str(parse_ts(args.at))] + src
    z = max(1.0, args.zoom)
    vf = (f"scale=1280:720:force_original_aspect_ratio=increase:flags=lanczos,crop=1280:720,"
          f"scale=iw*{z}:ih*{z},crop=1280:720,eq=contrast=1.08:saturation=1.2,unsharp=5:5:0.6")
    tmp = tempfile.mkdtemp()
    try:
        if args.text:
            lines = [ln if args.keep_case else ln.upper()
                     for ln in args.text.replace("\\n", "\n").split("\n")]
            fs = int(720 * args.size)
            step = int(fs * 1.15)
            block_h = len(lines) * step
            x = {"left": "60", "right": "w-tw-60"}.get(args.position, "(w-tw)/2")
            y0 = {"top": "50", "bottom": f"h-{block_h}-50"}.get(args.position, f"(h-{block_h})/2")
            for i, line in enumerate(lines):
                # textfile + expansion=none: no escaping headaches with : ' % \\ in titles
                tf = os.path.join(tmp, f"line{i}.txt")
                with open(tf, "w", encoding="utf-8") as f:
                    f.write(line)
                vf += (f",drawtext=fontfile={font}:textfile={tf}:expansion=none:fontsize={fs}:"
                       f"fontcolor={args.color}:borderw={max(4, fs // 12)}:bordercolor=black:"
                       f"shadowx=5:shadowy=5:shadowcolor=black@0.6:x={x}:y={y0}+{i * step}")
        for q in (2, 4, 6, 8):  # keep under YouTube's 2 MB limit
            run(["ffmpeg", "-y", *src, "-vf", vf, "-frames:v", "1", "-q:v", str(q), args.output])
            if os.path.getsize(args.output) < 2_000_000:
                break
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {args.output} (1280x720, {os.path.getsize(args.output) / 1e3:.0f} KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("video")
    c.add_argument("outdir")
    c.add_argument("--count", type=int, default=12)
    m = sub.add_parser("make")
    m.add_argument("source")
    m.add_argument("output")
    m.add_argument("--at", help="frame time when SOURCE is a video")
    m.add_argument("--text", help="overlay text; use \\n for a line break")
    m.add_argument("--keep-case", action="store_true", help="don't uppercase the text")
    m.add_argument("--position", choices=["left", "right", "center", "top", "bottom"], default="left")
    m.add_argument("--color", default="white", help="text color (name or 0xRRGGBB)")
    m.add_argument("--font")
    m.add_argument("--size", type=float, default=0.16, help="font size as a fraction of height")
    m.add_argument("--zoom", type=float, default=1.0, help="punch-in zoom, e.g. 1.2")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")
    candidates(args) if args.cmd == "candidates" else make(args)


if __name__ == "__main__":
    main()
