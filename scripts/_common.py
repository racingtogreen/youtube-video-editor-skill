"""Shared helpers for the youtube-video-editor scripts (ffmpeg/ffprobe wrappers)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def require(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        sys.exit(f"error: missing required tool(s): {', '.join(missing)}. "
                 "Install ffmpeg (e.g. `apt install ffmpeg` or `brew install ffmpeg`).")


def run(cmd, capture=False, quiet=True):
    """Run a command; exit with ffmpeg's stderr tail on failure."""
    if quiet and cmd and cmd[0] == "ffmpeg" and "-hide_banner" not in cmd:
        cmd = [cmd[0], "-hide_banner", "-nostdin"] + cmd[1:]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        sys.exit(f"error: command failed ({proc.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    return proc if capture else None


def probe(path):
    require("ffprobe")
    proc = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
               capture=True)
    return json.loads(proc.stdout)


def duration(path):
    return float(probe(path)["format"]["duration"])


def stream(info, kind):
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            return s
    return None


def fps_of(vstream):
    num, _, den = (vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "30/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


def default_font():
    """Best-effort bold sans font path for drawtext."""
    if shutil.which("fc-match"):
        p = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True)
        if p.returncode == 0 and os.path.exists(p.stdout.strip()):
            return p.stdout.strip()
    for cand in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/Library/Fonts/Arial Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(cand):
            return cand
    return None


def write_filter_script(graph):
    """Write a (possibly huge) filtergraph to a temp file for -filter_complex_script."""
    fd, path = tempfile.mkstemp(suffix=".ffgraph")
    with os.fdopen(fd, "w") as f:
        f.write(graph)
    return path


def fmt_ts(seconds, srt=False):
    """Seconds -> H:MM:SS / M:SS (YouTube style) or HH:MM:SS,mmm (SRT)."""
    if srt:
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(text):
    """'1:02:03.5' / '2:03' / '123.4' -> seconds."""
    parts = text.strip().replace(",", ".").split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


# Encoding settings that match YouTube's recommended upload specs.
YT_VIDEO = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-bf", "2", "-g", "60"]
YT_AUDIO = ["-c:a", "aac", "-b:a", "384k", "-ar", "48000"]
YT_CONTAINER = ["-movflags", "+faststart"]
# Fast intermediate settings (visually lossless, quick) for steps before the final export.
INTERMEDIATE_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]
INTERMEDIATE_AUDIO = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
