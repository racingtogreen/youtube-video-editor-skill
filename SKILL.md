---
name: youtube-video-editor
description: Edit raw footage into upload-ready YouTube videos and Shorts with ffmpeg - cut silences/dead air (jump cuts), trim, join intro/outro/b-roll clips, add ducked background music, transcribe and burn captions, normalize loudness to YouTube's -14 LUFS, reframe horizontal video to 9:16 Shorts, export with YouTube's recommended encoding, generate thumbnails, and write/validate chapters. Use this skill whenever the user wants to edit, cut, clean up, caption, subtitle, export, compress, reformat or "make ready for YouTube" any video file, turn a long video into Shorts/Reels/TikToks, make a thumbnail from a video, or create YouTube chapters/timestamps - even if they don't say "YouTube" or "ffmpeg" explicitly.
compatibility: Requires ffmpeg + ffprobe (with libx264, libass, libfreetype) and Python 3.8+. Captioning additionally needs faster-whisper (recommended: `python3 -m venv ~/.venvs/whisper && ~/.venvs/whisper/bin/pip install faster-whisper`; transcribe.py finds that venv automatically) and a one-time model download from huggingface.co.
---

# YouTube Video Editor

Turn raw recordings into publish-ready YouTube uploads using tested ffmpeg scripts in
`scripts/` (paths below are relative to this skill's directory, so prefix them with it when
running). Each script prints `--help` with every option; this file tells you which to use
and in what order.

## Before you start

1. Check tools: `ffmpeg -version`. If missing, tell the user how to install it
   (`brew install ffmpeg`, `apt install ffmpeg`, `winget install ffmpeg`) - don't try to
   edit video without it.
2. Inspect every input: `python scripts/probe.py INPUT --loudness`. This shows duration,
   resolution, fps, orientation, audio, HDR, and loudness. It decides several choices below
   (e.g. a vertical phone clip doesn't need Shorts reframing; a -25 LUFS file needs
   normalizing).
3. Clarify only what you can't infer. Reasonable defaults: long-form 16:9, cut silences
   for talking-head/tutorial content, -14 LUFS, captions as a separate .srt (not burned)
   for long-form, burned for Shorts.

Never overwrite the user's source files. Write into an output folder (e.g. `edit/` next
to the source) and keep intermediate files until the user is happy, so any step can be redone
without starting over.

## The pipeline

Run only the steps the request needs, in this order. The order matters: captions and
chapter times must be computed on the timeline as it is after the cuts, and loudness must be
measured on the final mix.

| # | Step | Script |
|---|------|--------|
| 1 | Remove dead air / jump cuts | `cut_silence.py` |
| 2 | Join intro, main, b-roll, outro, title cards; trim ranges | `assemble.py` |
| 3 | Background music, ducked under voice | `add_music.py` |
| 4 | Transcribe to captions + transcript | `transcribe.py` |
| 5 | Final export (reframe for Shorts, burn captions, loudness, encode) | `export.py` |
| 6 | Thumbnail | `thumbnail.py` |
| 7 | Chapters for the description | `chapters.py` |

Steps 1-3 write fast, high-quality intermediates; only step 5 does the slow final
encode, so run it once at the end.

### 1. Cut silences
```bash
python scripts/cut_silence.py raw.mp4 --dry-run              # preview what gets removed
python scripts/cut_silence.py raw.mp4 edit/cut.mp4 --edl edit/cut.json
```
Look at the "% removed" figure before rendering. Typical talking-head footage loses 10-30%.
If it's above ~40% or the user says words get clipped, raise `--padding` (0.25) or lower
`--threshold` (-40dB). A noisy room needs a higher threshold (-30dB). Keep the `--edl` file:
it's what lets chapter times written against the raw recording be remapped later.
Skip this step for music videos, vlogs with ambient sound, or anything where pauses are
intentional.

### 2. Assemble
```bash
python scripts/assemble.py edit/assembled.mp4 intro.mp4 edit/cut.mp4 broll.mov@0:05-0:12 outro.mp4 --fade 0.5
```
Mixed resolutions/frame rates/phones are normalized automatically (letterboxed, never
stretched). Use `--size 1080x1920` when assembling a vertical video. A still image
(`card.png@3`) becomes a 3-second silent title card.

### 3. Music
```bash
python scripts/add_music.py edit/assembled.mp4 music.mp3 edit/with_music.mp4 --music-db -20
```
-20 dB with ducking suits speech; use `--music-db -12 --no-duck` for montages without
speech. Remind the user that the music must be licensed (YouTube Audio Library is safe):
unlicensed tracks get Content ID claims.

### 4. Captions
```bash
python scripts/transcribe.py edit/with_music.mp4 --out edit/captions.srt            # long-form CC
python scripts/transcribe.py edit/short.mp4 --style shorts --out edit/short.srt     # punchy 1-4 word captions
```
Use `--model medium` or `large-v3` when accuracy matters and time allows, and `--language`
if known. Read the generated `.txt` transcript and fix obvious mis-hearings (names, jargon,
product names) in the .srt before burning. The transcript is also your source for
writing chapters, titles and descriptions.
If faster-whisper is missing, give the user the two venv install commands the script prints
(plain `pip` often doesn't exist on macOS, and Homebrew Python refuses global installs).
If the model can't download (offline/firewall), say so and offer to continue without
captions. Don't invent caption text.

### 5. Export
```bash
# Long-form: upload edit/captions.srt to YouTube separately (toggleable, searchable)
python scripts/export.py edit/with_music.mp4 edit/final.mp4

# Short from a section of a horizontal video
python scripts/export.py edit/with_music.mp4 edit/short.mp4 --format shorts \
    --start 2:10 --end 2:55 --reframe crop --crop-x 0.5 --captions edit/short.srt
```
For Shorts, choose the reframe deliberately: extract a frame
(`ffmpeg -ss T -i in.mp4 -frames:v 1 f.jpg`) and look at it. If the subject is off-center,
set `--crop-x` (0 = left edge ... 1 = right edge). If important content spans the whole
width (slides, screen recordings, two people), use `--reframe blur`. Shorts must be 3:00
or less; for clipping several Shorts from one video, pick self-contained moments with a
strong first 2 seconds (use the transcript to find them). When cutting a Short from the
uncut source, re-run `transcribe.py` on the exported clip rather than reusing long-form
captions.

Loudness lands at -14 LUFS unless the audio's peaks prevent it (true-peak ceiling -1 dBTP);
ending a little quieter is fine. YouTube only turns loud videos down, never quiet ones up,
so don't force it.

### 6. Thumbnail
```bash
python scripts/thumbnail.py candidates edit/final.mp4 edit/thumbs --count 12
python scripts/thumbnail.py make edit/final.mp4 edit/thumbnail.jpg --at 3:41 --text "10X FASTER\nWIFI" --color yellow --position left --zoom 1.1
```
Open `edit/thumbs/contact_sheet.jpg` with your image-viewing tool. Prefer a sharp frame
with a clear face/expression or subject and empty space on one side for text; avoid blur
and mid-blink frames. Put the text on the empty side (`--position`). Keep it to 2-5
words, complementary to the title (not a repeat of it). View the result image before
presenting it, and check that the text is readable and doesn't cover the subject. Offer
2-3 variants if the user hasn't specified text.

### 7. Chapters
Write chapters from the transcript (topic changes), as `M:SS Title` lines in a file, then:
```bash
python scripts/chapters.py edit/chapters.txt --video edit/final.mp4
python scripts/chapters.py raw_chapters.txt --edl edit/cut.json --video edit/final.mp4   # times from the RAW recording
```
The script enforces YouTube's rules (start at 0:00, at least 3 chapters, each at least 10 s) and
exits non-zero with the problems listed; fix and re-run. Give the user the printed list to
paste into the description. `--embed` additionally stores the chapters in the MP4, but
YouTube reads only the description.

## Wrapping up

Finish with a short summary for the user:
- the output files and where they are (final video, .srt, thumbnail, chapters text)
- what was done, with numbers (e.g. "removed 3:12 of dead air, 14:05 -> 10:53"; "loudness -21 -> -14 LUFS")
- anything they should check by eye/ear (e.g. a jump cut that may feel abrupt, caption names)
- upload tips that apply: upload the .srt under Subtitles, paste chapters into the description,
  set the custom thumbnail

## When something goes wrong

- **Script errors** show the tail of ffmpeg's log. Read it: common causes are a missing
  file, a variable-frame-rate phone video (re-run through `assemble.py` first; it
  conforms fps), or no audio stream.
- **Audio/video drift after cuts** usually means VFR source: conform with
  `assemble.py out.mp4 in.mp4 --fps 30` first, then cut.
- **HDR (iPhone HLG/Dolby Vision) looks washed out**: probe shows `HDR`. Tone-map to SDR
  before editing; see `references/ffmpeg_recipes.md`.
- Anything the scripts don't cover (speed ramps, picture-in-picture, crossfades between
  clips, color, zoom-punch-ins, watermark/logo, GIF previews, splitting long files):
  see `references/ffmpeg_recipes.md`, and `references/youtube_specs.md` for upload specs.
