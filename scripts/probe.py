#!/usr/bin/env python3
"""Summarize a media file: duration, video/audio format, and (optionally) loudness.

Usage:
  probe.py INPUT [--loudness] [--json]

--loudness measures integrated loudness (LUFS), true peak and LRA with ffmpeg's
loudnorm analyzer, so you can tell whether normalization is needed
(YouTube plays back at about -14 LUFS).
"""
import argparse
import json
import re

from _common import fmt_ts, fps_of, probe, require, run, stream


def measure_loudness(path):
    proc = run(["ffmpeg", "-i", path, "-vn", "-af",
                "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
               capture=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not m:
        return None
    d = json.loads(m.group(0))
    return {"integrated_lufs": float(d["input_i"]), "true_peak_dbtp": float(d["input_tp"]),
            "lra_lu": float(d["input_lra"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--loudness", action="store_true", help="also measure loudness (slower)")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")

    info = probe(args.input)
    fmt = info["format"]
    v, a = stream(info, "video"), stream(info, "audio")
    out = {"file": args.input, "duration_s": round(float(fmt.get("duration", 0)), 3),
           "size_mb": round(int(fmt.get("size", 0)) / 1e6, 2),
           "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000)}
    if v:
        rot = 0
        for sd in v.get("side_data_list", []):
            rot = int(sd.get("rotation", rot) or rot)
        rot = int(v.get("tags", {}).get("rotate", rot))
        out["video"] = {"codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
                        "fps": round(fps_of(v), 3), "pix_fmt": v.get("pix_fmt"), "rotation": rot,
                        "color_transfer": v.get("color_transfer")}
        w, h = v.get("width", 0), v.get("height", 0)
        if abs(rot) in (90, 270):
            w, h = h, w
        out["video"]["display_orientation"] = "vertical" if h > w else "horizontal" if w > h else "square"
    if a:
        out["audio"] = {"codec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate", 0)),
                        "channels": a.get("channels")}
    if args.loudness and a:
        out["loudness"] = measure_loudness(args.input)

    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{out['file']}: {fmt_ts(out['duration_s'])} ({out['duration_s']}s), "
          f"{out['size_mb']} MB, {out['bitrate_kbps']} kb/s")
    if v:
        vv = out["video"]
        print(f"  video: {vv['codec']} {vv['width']}x{vv['height']} @ {vv['fps']} fps, {vv['pix_fmt']}, "
              f"{vv['display_orientation']}" + (f", rotation {vv['rotation']}" if vv["rotation"] else "")
              + (", HDR (" + vv["color_transfer"] + ")" if vv["color_transfer"] in ("smpte2084", "arib-std-b67") else ""))
    else:
        print("  video: none")
    print(f"  audio: {a.get('codec_name')} {out['audio']['sample_rate']} Hz, {a.get('channels')} ch" if a else "  audio: none")
    if out.get("loudness"):
        L = out["loudness"]
        print(f"  loudness: {L['integrated_lufs']} LUFS integrated, {L['true_peak_dbtp']} dBTP peak, "
              f"{L['lra_lu']} LU range")


if __name__ == "__main__":
    main()
