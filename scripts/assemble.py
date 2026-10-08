#!/usr/bin/env python3
"""Join clips (intro, main recording, b-roll, outro, title cards) into one timeline.

Usage:
  assemble.py OUTPUT CLIP [CLIP ...] [--size 1920x1080] [--fps 30] [--fade 0.5]

CLIP forms:
  video.mp4                 whole clip
  video.mp4@1:05-3:20       only 1:05 to 3:20 (any of S, M:SS, H:MM:SS, decimals ok)
  video.mp4@90-             from 90s to the end
  card.png@4                still image shown for 4 seconds (silent)

Every clip is scaled to fit --size (letterboxed/pillarboxed, never stretched), converted to
--fps and 48 kHz stereo, so clips from different cameras/phones/screen recorders join
cleanly. Clips without audio get silence. --fade adds a fade from/to black at the very
start and end of the result.
"""
import argparse
import os

from _common import (INTERMEDIATE_AUDIO, INTERMEDIATE_VIDEO, duration, fmt_ts, parse_ts, probe,
                     require, run, stream, write_filter_script)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def parse_clip(spec):
    path, _, rng = spec.partition("@")
    if not os.path.exists(path):
        raise SystemExit(f"error: clip not found: {path}")
    is_image = os.path.splitext(path)[1].lower() in IMAGE_EXT
    if is_image:
        return {"path": path, "image": True, "dur": parse_ts(rng) if rng else 3.0}
    start, end = 0.0, None
    if rng:
        a, _, b = rng.partition("-")
        start = parse_ts(a) if a else 0.0
        end = parse_ts(b) if b else None
    return {"path": path, "image": False, "start": start, "end": end}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--size", default="1920x1080", help="WxH of the result (default 1920x1080)")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--fade", type=float, default=0.0, help="fade in/out from black, seconds")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")
    W, H = (int(x) for x in args.size.lower().split("x"))

    clips = [parse_clip(c) for c in args.clips]
    inputs, chains, labels, total = [], [], [], 0.0
    for i, c in enumerate(clips):
        norm = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,fps={args.fps},format=yuv420p")
        if c["image"]:
            inputs += ["-loop", "1", "-t", str(c["dur"]), "-i", c["path"]]
            chains.append(f"[{i}:v]{norm},setpts=PTS-STARTPTS[v{i}]")
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={c['dur']}[a{i}]")
            total += c["dur"]
        else:
            info = probe(c["path"])
            if not stream(info, "video"):
                raise SystemExit(f"error: {c['path']} has no video stream")
            end = c["end"] if c["end"] is not None else float(info["format"]["duration"])
            d = end - c["start"]
            if d <= 0:
                raise SystemExit(f"error: empty range for {c['path']}")
            inputs += ["-ss", str(c["start"]), "-t", str(d), "-i", c["path"]]
            chains.append(f"[{i}:v]{norm},setpts=PTS-STARTPTS[v{i}]")
            if stream(info, "audio"):
                chains.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
            else:
                chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f}[a{i}]")
            total += d
        labels.append(f"[v{i}][a{i}]")

    graph = chains + ["".join(labels) + f"concat=n={len(clips)}:v=1:a=1[cv][ca]"]
    vout, aout = "[cv]", "[ca]"
    if args.fade > 0:
        f, st = args.fade, max(0.0, total - args.fade)
        graph.append(f"[cv]fade=t=in:d={f},fade=t=out:st={st:.3f}:d={f}[fv]")
        graph.append(f"[ca]afade=t=in:d={f},afade=t=out:st={st:.3f}:d={f}[fa]")
        vout, aout = "[fv]", "[fa]"

    script = write_filter_script(";\n".join(graph))
    try:
        run(["ffmpeg", "-y", *inputs, "-filter_complex_script", script, "-map", vout, "-map", aout,
             *INTERMEDIATE_VIDEO, *INTERMEDIATE_AUDIO, args.output])
    finally:
        os.unlink(script)
    print(f"wrote {args.output} ({fmt_ts(duration(args.output))}, {len(clips)} clips, {W}x{H}@{args.fps:g})")


if __name__ == "__main__":
    main()
