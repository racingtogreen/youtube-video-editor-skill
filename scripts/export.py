#!/usr/bin/env python3
"""Final YouTube export: reframe, burn captions, normalize loudness, encode to spec.

Usage:
  export.py INPUT OUTPUT [--format long|shorts] [--reframe crop|blur] [--crop-x 0.5]
            [--captions subs.srt] [--lufs -14] [--no-loudnorm]
            [--start T] [--end T] [--max-height 2160] [--crf 18]

--format long   : keeps the source frame (even dimensions), optional --max-height downscale.
--format shorts : 1080x1920 vertical. Horizontal sources are reframed with
                  --reframe crop  (fill the frame; --crop-x 0..1 picks the horizontal
                                   position, 0=left edge, 0.5=center, 1=right edge) or
                  --reframe blur  (whole frame centered over a blurred, zoomed copy).
--captions      : burns an .srt into the picture (styled per format). For normal long-form
                  videos prefer uploading the .srt to YouTube instead (viewers can toggle it,
                  and it is indexed for search) - burn only when asked or for Shorts.
Loudness is normalized with two-pass EBU R128 loudnorm to --lufs (default -14 LUFS, -1 dBTP),
which is what YouTube normalizes playback to.
Output: H.264 High / yuv420p / AAC 48 kHz / +faststart MP4, as YouTube recommends.
"""
import argparse
import json
import os
import re
import shutil
import tempfile

from _common import (YT_AUDIO, YT_CONTAINER, YT_VIDEO, duration, fmt_ts, parse_ts, probe,
                     require, run, stream)

CAPTION_STYLE = {
    "long": "Fontname=DejaVu Sans,Fontsize=18,Outline=1.6,Shadow=0,MarginV=18",
    "shorts": ("Fontname=DejaVu Sans,Fontsize=13,Bold=1,Outline=2.2,Shadow=0,Alignment=2,MarginV=75,"
               "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000"),
}


def measure(path, trim, target, tp, lra):
    proc = run(["ffmpeg", *trim, "-i", path, "-vn", "-af",
                f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
               capture=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def video_filter(v, fmt, reframe, crop_x, max_height):
    w, h = v["width"], v["height"]
    rot = 0
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) in (90, 270):  # ffmpeg auto-rotates; reason about the displayed shape
        w, h = h, w
    if fmt == "long":
        if max_height and h > max_height:
            return f"scale=-2:{max_height}:flags=lanczos,setsar=1"
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    # shorts
    if h * 9 >= w * 16 * 0.98:  # already vertical (or close): fit into 1080x1920
        return ("scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    if reframe == "crop":
        return (f"crop=trunc(ih*9/16/2)*2:ih:(iw-ih*9/16)*{crop_x}:0,"
                "scale=1080:1920:flags=lanczos,setsar=1")
    return ("split[bgsrc][fgsrc];"
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.08[bg];"
            "[fgsrc]scale=1080:-2:flags=lanczos[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--format", choices=["long", "shorts"], default="long")
    ap.add_argument("--reframe", choices=["crop", "blur"], default="crop")
    ap.add_argument("--crop-x", type=float, default=0.5)
    ap.add_argument("--captions", help=".srt file to burn in")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--start", help="trim: start time")
    ap.add_argument("--end", help="trim: end time")
    ap.add_argument("--max-height", type=int, help="downscale long-form video taller than this")
    ap.add_argument("--crf", type=int, default=18, help="quality, lower=better (default 18)")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")
    if not 0 <= args.crop_x <= 1:
        ap.error("--crop-x must be between 0 and 1")

    info = probe(args.input)
    v, a = stream(info, "video"), stream(info, "audio")
    if not v:
        raise SystemExit("error: input has no video stream")
    trim = []
    start = parse_ts(args.start) if args.start else 0.0
    if args.start:
        trim += ["-ss", str(start)]
    if args.end:
        trim += ["-t", str(parse_ts(args.end) - start)]

    vf = video_filter(v, args.format, args.reframe, args.crop_x, args.max_height)
    tmpdir = tempfile.mkdtemp()
    try:
        if args.captions:
            # Copy to a plain path so the subtitles filter needs no escaping.
            srt = os.path.join(tmpdir, "subs.srt")
            shutil.copy(args.captions, srt)
            if args.start:  # captions are timed to the untrimmed input
                vf += f",setpts=PTS+{start}/TB,subtitles={srt}:force_style='{CAPTION_STYLE[args.format]}',setpts=PTS-STARTPTS"
            else:
                vf += f",subtitles={srt}:force_style='{CAPTION_STYLE[args.format]}'"

        cmd = ["ffmpeg", "-y", *trim, "-i", args.input, "-filter_complex", f"[0:v]{vf}[vout]",
               "-map", "[vout]"]
        enc_video = list(YT_VIDEO)
        enc_video[enc_video.index("-crf") + 1] = str(args.crf)
        if a:
            cmd += ["-map", "0:a:0"]
            if not args.no_loudnorm:
                m = measure(args.input, trim, args.lufs, -1.0, 11)
                if m and m["input_i"] not in ("-inf", "inf"):
                    print(f"loudness before: {m['input_i']} LUFS, peak {m['input_tp']} dBTP")
                    cmd += ["-af", (f"loudnorm=I={args.lufs}:TP=-1:LRA=11:measured_I={m['input_i']}:"
                                    f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
                                    f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
                                    "linear=true,aresample=48000")]
                else:
                    print("warning: audio is silent; skipping loudness normalization")
            cmd += YT_AUDIO
        cmd += enc_video + YT_CONTAINER + [args.output]
        run(cmd)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    out = probe(args.output)
    ov = stream(out, "video")
    d = duration(args.output)
    print(f"wrote {args.output}: {ov['width']}x{ov['height']}, {fmt_ts(d)}, "
          f"{int(out['format']['size']) / 1e6:.1f} MB")
    if args.format == "shorts" and d > 180:
        print(f"warning: {fmt_ts(d)} is longer than 3:00 - YouTube will not treat it as a Short")


if __name__ == "__main__":
    main()
