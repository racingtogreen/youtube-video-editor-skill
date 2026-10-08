#!/usr/bin/env python3
"""Add a background music bed that ducks automatically under the voice.

Usage:
  add_music.py VIDEO MUSIC OUTPUT [--music-db -20] [--no-duck] [--fade 2]
               [--start 0] [--end END]

The music is looped to cover the video, lowered by --music-db, faded in/out over --fade
seconds, and (unless --no-duck) side-chain compressed by the voice so it dips further
whenever someone talks. --start/--end limit the music to part of the video (seconds or
M:SS). Video is stream-copied (no re-encode).

Only use music the creator has the rights to (YouTube Audio Library, licensed tracks);
Content ID claims can demonetize or block a video.
"""
import argparse

from _common import duration, parse_ts, probe, require, run, stream


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("music")
    ap.add_argument("output")
    ap.add_argument("--music-db", type=float, default=-20, help="music gain in dB (default -20)")
    ap.add_argument("--no-duck", action="store_true", help="disable ducking under speech")
    ap.add_argument("--fade", type=float, default=2.0, help="music fade in/out seconds")
    ap.add_argument("--start", default="0", help="music starts here in the video")
    ap.add_argument("--end", help="music ends here in the video (default: video end)")
    args = ap.parse_args()
    require("ffmpeg", "ffprobe")

    total = duration(args.video)
    start = parse_ts(args.start)
    end = min(parse_ts(args.end), total) if args.end else total
    span = end - start
    if span <= 0:
        raise SystemExit("error: --end must be after --start")
    has_voice = stream(probe(args.video), "audio") is not None
    fade = min(args.fade, span / 2)
    delay_ms = int(start * 1000)

    music = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={span:.3f},"
             f"volume={args.music_db}dB,afade=t=in:d={fade},afade=t=out:st={span - fade:.3f}:d={fade},"
             f"adelay={delay_ms}|{delay_ms},apad=whole_dur={total:.3f}[m]")
    if not has_voice:
        graph = music + ";[m]anull[out]"
    elif args.no_duck:
        graph = (music + ";[0:a]aresample=48000,aformat=channel_layouts=stereo[v];"
                 "[v][m]amix=inputs=2:duration=first:normalize=0[out]")
    else:
        graph = (music + ";[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v][sc];"
                 "[m][sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[ducked];"
                 "[v][ducked]amix=inputs=2:duration=first:normalize=0[out]")
    run(["ffmpeg", "-y", "-i", args.video, "-stream_loop", "-1", "-i", args.music,
         "-filter_complex", graph, "-map", "0:v", "-map", "[out]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-t", f"{total:.3f}", args.output])
    print(f"wrote {args.output} (music {args.music_db} dB, {'ducked' if has_voice and not args.no_duck else 'no ducking'})")


if __name__ == "__main__":
    main()
