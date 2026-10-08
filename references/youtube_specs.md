# YouTube upload specs (cheat sheet)

`export.py` already applies the encoding settings below. Use this file to answer
questions or to check a file the user produced elsewhere.

## Recommended encoding
| Setting | Value |
|---|---|
| Container | MP4, `moov` atom at front (`-movflags +faststart`) |
| Video codec | H.264, High profile, progressive, 4:2:0 (`yuv420p`), 2 consecutive B-frames, closed GOP of half the frame rate |
| Frame rate | Same as recorded (24/25/30/48/50/60). Don't convert 30 to 60. |
| Audio | AAC-LC, 48 kHz (or 44.1), stereo or 5.1. 384 kb/s stereo recommended |
| Loudness | YouTube normalizes playback to about -14 LUFS (it only turns loud content down) |

Recommended SDR video bitrates (H.264, upload):

| Resolution | 24-30 fps | 48-60 fps |
|---|---|---|
| 2160p (4K) | 35-45 Mb/s | 53-68 Mb/s |
| 1440p | 16 Mb/s | 24 Mb/s |
| 1080p | 8 Mb/s | 12 Mb/s |
| 720p | 5 Mb/s | 7.5 Mb/s |

`export.py` uses CRF 18 (quality-based), which typically meets or exceeds these. Raise
`--crf` to 20-23 only if the user needs a smaller file.
Uploading at 1440p or 4K gets the more efficient VP9/AV1 processing on YouTube's side,
which looks noticeably better even for 1080p viewers. An upscale on export
(`scale=-2:2160:flags=lanczos`) is a known creator trick if the user asks about quality.

## Aspect ratios
- Long-form: 16:9 (1920x1080, 2560x1440, 3840x2160). Other ratios are allowed; the
  player adapts.
- Shorts: vertical 9:16 (1080x1920) or square, **max 3 minutes**. Keep captions and key
  content out of the bottom ~20% and right ~15% (UI overlays: title, buttons).

## Thumbnails
1280x720 (16:9), minimum width 640 px, JPG/PNG/GIF, **under 2 MB**. The bottom-right
corner is covered by the duration badge.

## Chapters (description timestamps)
- First timestamp must be `0:00`
- At least 3 timestamps, ascending
- Each chapter at least 10 seconds
- Format: `0:00 Intro` per line (H:MM:SS for videos over an hour)

## Captions
Upload `.srt` (or `.vtt`) under *Subtitles*. Uploaded captions beat auto-captions for
accuracy, are toggleable, and are indexed. Reading-speed rule of thumb: at most 2 lines,
about 42 characters per line, 1-7 s per caption.

## Limits
- Max file size 256 GB or 12 hours, whichever is less.
- Videos over 15 minutes require a verified account.
