# YouTube Video Editor — a Claude skill

A [Claude skill](https://docs.claude.com/en/docs/claude-code/skills) that turns raw footage into
upload-ready YouTube videos and Shorts using ffmpeg. Describe the edit in plain English and
Claude runs the right steps:

- **Jump cuts**: remove silences and dead air
- **Assemble**: intro, main, b-roll, outro, title cards (mixed cameras/phones are normalized)
- **Music**: background track that ducks under speech
- **Captions**: Whisper transcription to `.srt` + timestamped transcript
- **Shorts**: 1080×1920 reframe (crop or blurred background) with burned-in captions
- **Export**: YouTube-recommended H.264/AAC encoding, loudness normalized to -14 LUFS
- **Thumbnails**: candidate frames + 1280×720 thumbnail with bold text
- **Chapters**: validated against YouTube's rules, remapped after cuts

## Install

**Claude Code (all projects):**
```bash
git clone https://github.com/racingtogreen/youtube-video-editor-skill.git ~/.claude/skills/youtube-video-editor
```
For a single project, clone into that project's `.claude/skills/youtube-video-editor` instead.

**Claude app / claude.ai:** zip this folder (or use a packaged `youtube-video-editor.skill`)
and upload it under *Settings → Capabilities → Skills*.

## Requirements

- **ffmpeg**: `brew install ffmpeg` (Mac), `winget install ffmpeg` (Windows), `sudo apt install ffmpeg` (Linux)
- **Python 3.8+**
- **Captions only**: faster-whisper, installed in its own environment (the skill finds it automatically):
  ```bash
  python3 -m venv ~/.venvs/whisper
  ~/.venvs/whisper/bin/pip install faster-whisper
  ```
  The first transcription downloads a speech model (~500 MB) from huggingface.co.

## Usage

Just ask Claude, for example:

> Edit `raw.mp4` for YouTube: cut out the silences, add captions, and make a thumbnail that
> says "WiFi in 10 minutes". Then give me chapters for the description.

> Turn 2:10–2:55 of `final.mp4` into a Short with big captions. I'm on the left of the frame.

Output goes to an `edit/` folder next to your video; source files are never modified.

## Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Instructions Claude follows (pipeline order, tuning, wrap-up) |
| `scripts/` | Tested ffmpeg wrappers: `probe`, `cut_silence`, `assemble`, `add_music`, `transcribe`, `export`, `thumbnail`, `chapters` (each has `--help`) |
| `references/` | YouTube upload specs and extra ffmpeg recipes (speed ramps, crossfades, PiP, logos, HDR→SDR, denoise, blur…) |
