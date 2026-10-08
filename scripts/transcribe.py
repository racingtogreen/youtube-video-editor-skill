#!/usr/bin/env python3
"""Transcribe a video to SRT captions (+ a timestamped transcript) with Whisper.

Usage:
  transcribe.py INPUT [--out captions.srt] [--model small] [--language en]
                [--max-chars 42] [--max-lines 2] [--style long|shorts]

Requires `faster-whisper` (pip install faster-whisper). Model sizes: tiny, base, small
(default, good on CPU), medium, large-v3 (best, slow on CPU).

Captions are rebuilt from word timestamps so they're readable:
  --style long   : up to 2 lines x 42 chars, ~1-7 s each (standard YouTube CC)
  --style shorts : 1 short line of 1-4 words, for burned-in, punchy Shorts captions
Also writes <out>.txt: one line per caption with its start time, handy for writing
chapters, titles and descriptions.

Transcribe AFTER cutting silences, so caption times match the edited video.
"""
import argparse
import os
import sys

from _common import fmt_ts, require, run


def load_words(path, model_name, language):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("error: faster-whisper is not installed. Run: pip install faster-whisper")
    try:
        model = WhisperModel(model_name, device="auto", compute_type="auto")
    except Exception as e:  # usually: model download blocked / offline
        sys.exit(f"error: could not load Whisper model '{model_name}': {e}\n"
                 "The first run downloads the model from huggingface.co. If offline, download it "
                 "elsewhere and pass its local folder with --model /path/to/model.")
    segments, info = model.transcribe(path, language=language, word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"start": w.start, "end": w.end, "text": w.word})
        # a segment boundary is a natural sentence break
        if words:
            words[-1]["break"] = True
    print(f"detected language: {info.language} ({info.language_probability:.0%})", file=sys.stderr)
    return words


def group(words, max_chars, max_lines, max_dur, max_words):
    cues, cur = [], []

    def flush():
        if cur:
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                         "text": "".join(w["text"] for w in cur).strip()})
            cur.clear()

    limit = max_chars * max_lines
    for w in words:
        text = "".join(x["text"] for x in cur) + w["text"]
        too_long = len(text.strip()) > limit or (cur and w["end"] - cur[0]["start"] > max_dur)
        if cur and (too_long or len(cur) >= max_words):
            flush()
        cur.append(w)
        if w.get("break") or w["text"].rstrip().endswith((".", "?", "!")):
            flush()
    flush()
    for i, c in enumerate(cues):  # avoid overlaps, keep a minimum on-screen time
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else c["end"] + 1
        c["end"] = min(max(c["end"], c["start"] + 0.7), nxt)
        c["text"] = wrap(c["text"], max_chars, max_lines)
    return cues


def wrap(text, max_chars, max_lines):
    if len(text) <= max_chars or max_lines == 1:
        return text
    words, best = text.split(), None
    for i in range(1, len(words)):  # most balanced 2-line split
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, a + "\n" + b)
    return best[1] if best else text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", help="SRT path (default: INPUT basename + .srt)")
    ap.add_argument("--model", default="small", help="model size or local model folder")
    ap.add_argument("--language", help="e.g. en, es, de (default: auto-detect)")
    ap.add_argument("--style", choices=["long", "shorts"], default="long")
    ap.add_argument("--max-chars", type=int)
    ap.add_argument("--max-lines", type=int)
    args = ap.parse_args()
    require("ffmpeg")

    out = args.out or os.path.splitext(args.input)[0] + ".srt"
    if args.style == "shorts":
        max_chars, max_lines, max_dur, max_words = args.max_chars or 18, args.max_lines or 1, 2.0, 4
    else:
        max_chars, max_lines, max_dur, max_words = args.max_chars or 42, args.max_lines or 2, 7.0, 99

    # Extract 16 kHz mono audio first: faster and avoids decoder quirks with odd containers.
    wav = out + ".tmp.wav"
    run(["ffmpeg", "-y", "-i", args.input, "-vn", "-ac", "1", "-ar", "16000", wav])
    try:
        words = load_words(wav, args.model, args.language)
    finally:
        os.unlink(wav)
    if not words:
        sys.exit("error: no speech detected")
    cues = group(words, max_chars, max_lines, max_dur, max_words)

    with open(out, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{fmt_ts(c['start'], srt=True)} --> {fmt_ts(c['end'], srt=True)}\n{c['text']}\n\n")
    with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as f:
        for c in cues:
            f.write(f"[{fmt_ts(c['start'])}] {c['text'].replace(chr(10), ' ')}\n")
    print(f"wrote {out} ({len(cues)} captions) and {os.path.splitext(out)[0]}.txt")


if __name__ == "__main__":
    main()
