#!/usr/bin/env python3
"""Remove dead air (jump cuts) from a talking-head / screen-recording video.

Usage:
  cut_silence.py INPUT OUTPUT [--threshold -35dB] [--min-silence 0.6] [--padding 0.15]
                 [--min-keep 0.25] [--edl cuts.json] [--dry-run]

How it works: ffmpeg's silencedetect finds stretches quieter than --threshold that last
at least --min-silence seconds. Each silence is shrunk by --padding on both sides (so words
aren't clipped), the remaining "keep" segments are trimmed and concatenated, and each joint
gets a 10 ms audio fade to avoid clicks.

--edl writes the keep-segment list as JSON. Pass it to chapters.py --edl to convert
timestamps from the original recording to the edited timeline.
--dry-run prints what would be removed without rendering.

Tuning: noisy room -> raise threshold (e.g. -30dB). Words getting clipped -> raise
--padding to 0.25. Pacing still slow -> lower --min-silence to 0.4.
"""
import argparse
import json
import os
import re

from _common import (INTERMEDIATE_AUDIO, INTERMEDIATE_VIDEO, duration, fmt_ts, probe, require,
                     run, stream, write_filter_script)


def detect_silences(path, threshold, min_silence):
    proc = run(["ffmpeg", "-i", path, "-vn", "-af",
                f"silencedetect=noise={threshold}:d={min_silence}", "-f", "null", "-"], capture=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return starts, ends


def keep_segments(starts, ends, total, padding, min_keep):
    if len(ends) < len(starts):          # file ends while silent
        ends.append(total)
    segs, cursor = [], 0.0
    for s, e in zip(starts, ends):
        s = max(0.0, s)
        cut_from = s + padding if s > 0 else 0.0
        cut_to = e - padding if e < total else total
        if cut_to <= cut_from:
            continue
        if cut_from > cursor:
            segs.append([cursor, cut_from])
        cursor = cut_to
    if cursor < total:
        segs.append([cursor, total])
    return [[round(a, 3), round(b, 3)] for a, b in segs if b - a >= min_keep]


def render(path, out, segs, has_audio):
    fade = 0.01
    parts, labels = [], []
    for i, (a, b) in enumerate(segs):
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
        if has_audio:
            d = b - a
            parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={fade},afade=t=out:st={max(0, d - fade):.3f}:d={fade}[a{i}]")
            labels.append(f"[a{i}]")
    n = len(segs)
    parts.append("".join(labels) + f"concat=n={n}:v=1:a={1 if has_audio else 0}"
                 + ("[outv][outa]" if has_audio else "[outv]"))
    script = write_filter_script(";\n".join(parts))
    try:
        cmd = ["ffmpeg", "-y", "-i", path, "-filter_complex_script", script, "-map", "[outv]"]
        if has_audio:
            cmd += ["-map", "[outa]"] + INTERMEDIATE_AUDIO
        run(cmd + INTERMEDIATE_VIDEO + [out])
    finally:
        os.unlink(script)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--threshold", default="-35dB", help="silence level (default -35dB)")
    ap.add_argument("--min-silence", type=float, default=0.6, help="min silence length to cut, s")
    ap.add_argument("--padding", type=float, default=0.15, help="silence kept around speech, s")
    ap.add_argument("--min-keep", type=float, default=0.25, help="drop keep-segments shorter than this, s")
    ap.add_argument("--edl", help="write keep segments JSON here")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")
    if not args.dry_run and not args.output:
        ap.error("OUTPUT is required unless --dry-run")

    info = probe(args.input)
    if not stream(info, "audio"):
        raise SystemExit("error: input has no audio track; nothing to detect silence on")
    total = duration(args.input)
    starts, ends = detect_silences(args.input, args.threshold, args.min_silence)
    segs = keep_segments(starts, ends, total, args.padding, args.min_keep)
    if not segs:
        raise SystemExit("error: everything is below the threshold; try a lower --threshold (e.g. -45dB)")
    kept = sum(b - a for a, b in segs)
    print(f"{len(starts)} silences found; keeping {len(segs)} segments: "
          f"{fmt_ts(total)} -> {fmt_ts(kept)} ({100 * (1 - kept / total):.1f}% removed)")

    if args.edl:
        with open(args.edl, "w") as f:
            json.dump({"source": os.path.abspath(args.input), "source_duration": total,
                       "keep": segs}, f, indent=1)
        print(f"wrote EDL {args.edl}")
    if args.dry_run:
        for a, b in segs[:40]:
            print(f"  keep {fmt_ts(a)} ({a:.2f}) - {fmt_ts(b)} ({b:.2f})")
        if len(segs) > 40:
            print(f"  ... {len(segs) - 40} more")
        return
    render(args.input, args.output, segs, has_audio=True)
    print(f"wrote {args.output} ({fmt_ts(duration(args.output))})")


if __name__ == "__main__":
    main()
