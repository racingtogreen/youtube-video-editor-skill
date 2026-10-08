#!/usr/bin/env python3
"""Validate YouTube chapters, remap them after edits, and optionally embed them in the MP4.

Usage:
  chapters.py CHAPTERS_FILE [--edl cuts.json] [--duration SECONDS | --video final.mp4]
              [--embed final.mp4 --out final_ch.mp4]

CHAPTERS_FILE has one chapter per line, "<time> <title>", e.g.
  0:00 Intro
  1:32 Setting up the router
  12:05 Results
(A JSON list of {"time": ..., "title": ...} also works.)

--edl     : times are from the ORIGINAL recording; convert them to the edited timeline using
            the keep-segment list written by cut_silence.py --edl. A chapter that falls inside
            a removed stretch snaps to the next kept moment.
--video / --duration : lets the script check the last chapter is long enough.
--embed   : also writes chapter markers into the MP4 container (shown by VLC etc.). YouTube
            itself ONLY reads chapters from the description, so always paste the printed list.

YouTube's rules (checked here): first chapter at 0:00, at least 3 chapters, each at least
10 seconds, ascending order.
"""
import argparse
import json
import os
import re
import sys
import tempfile

from _common import duration, fmt_ts, parse_ts, require, run


def load(path):
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):
        return [(parse_ts(str(c["time"])), c["title"].strip()) for c in json.loads(text)]
    items = []
    for line in text.splitlines():
        m = re.match(r"\s*[-*]?\s*\(?(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)\)?\s*[-–—:|]?\s*(.+)", line)
        if m:
            items.append((parse_ts(m.group(1)), m.group(2).strip()))
    return items


def remap(t, keep):
    """Original-timeline time -> edited-timeline time."""
    out = 0.0
    for a, b in keep:
        if t < a:
            return out          # inside a removed gap: snap to next kept moment
        if t <= b:
            return out + (t - a)
        out += b - a
    return out


def validate(chs, total):
    problems = []
    if not chs or chs[0][0] != 0:
        problems.append("first chapter must start at 0:00")
    if len(chs) < 3:
        problems.append(f"need at least 3 chapters (have {len(chs)})")
    for i, (t, title) in enumerate(chs):
        end = chs[i + 1][0] if i + 1 < len(chs) else total
        if end is not None and end - t < 10:
            problems.append(f"'{title}' at {fmt_ts(t)} is shorter than 10 s ({end - t:.1f} s)")
        if i and t <= chs[i - 1][0]:
            problems.append(f"'{title}' at {fmt_ts(t)} is not after the previous chapter")
    return problems


def embed(video, out, chs, total):
    meta = [";FFMETADATA1"]
    for i, (t, title) in enumerate(chs):
        end = chs[i + 1][0] if i + 1 < len(chs) else total
        safe = re.sub(r"([=;#\\])", r"\\\1", title)
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(t * 1000)}", f"END={int(end * 1000)}",
                 f"title={safe}"]
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(meta) + "\n")
    try:
        run(["ffmpeg", "-y", "-i", video, "-i", path, "-map", "0", "-map_metadata", "0",
             "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", out])
    finally:
        os.unlink(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chapters")
    ap.add_argument("--edl")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--video")
    ap.add_argument("--embed", help="video to embed chapter markers into")
    ap.add_argument("--out", help="output path for --embed")
    args = ap.parse_args()

    chs = load(args.chapters)
    if args.edl:
        keep = json.load(open(args.edl))["keep"]
        chs = [(round(remap(t, keep), 2), title) for t, title in chs]
    chs.sort(key=lambda c: c[0])
    if chs and 0 < chs[0][0] < 1:  # rounding/padding drift on the first chapter
        chs[0] = (0.0, chs[0][1])

    total = args.duration
    if args.video or args.embed:
        require("ffprobe")
        total = duration(args.video or args.embed)

    print("Paste into the YouTube description:\n")
    for t, title in chs:
        print(f"{fmt_ts(t)} {title}")
    problems = validate(chs, total)
    if problems:
        print("\nProblems (YouTube will ignore the chapters until fixed):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
    if args.embed:
        if not args.out:
            ap.error("--embed needs --out")
        require("ffmpeg")
        embed(args.embed, args.out, chs, total)
        print(f"\nembedded {len(chs)} chapters into {args.out}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
