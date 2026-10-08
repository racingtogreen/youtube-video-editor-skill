# ffmpeg recipes beyond the bundled scripts

Each recipe works as written with ffmpeg 6+. Re-encode with intermediate quality
(`-c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p -c:a aac -b:a 320k`) and leave the
final encode to `scripts/export.py`.

## Contents
1. Quick trim without re-encoding
2. Speed up / slow down a section
3. Crossfade between two clips
4. Picture-in-picture (facecam over screen recording)
5. Logo / watermark
6. Zoom punch-in on a section
7. Text callout / lower third
8. Basic color: brightness, contrast, saturation, LUT
9. HDR (iPhone) to SDR
10. Denoise voice / remove hum
11. Split a long recording into parts
12. Extract audio / replace audio
13. GIF / preview clip
14. Blur a region (hide private info)

---

### 1. Quick trim without re-encoding
```bash
ffmpeg -ss 0:30 -to 5:00 -i in.mp4 -c copy -avoid_negative_ts make_zero out.mp4
```
Cuts land on the nearest keyframe (can be off by a second or so). For frame-accurate
trims, use `assemble.py out.mp4 in.mp4@0:30-5:00`.

### 2. Speed up / slow down a section (e.g. 2x through a boring install)
```bash
ffmpeg -i in.mp4 -filter_complex "
[0:v]trim=0:60,setpts=PTS-STARTPTS[v1];[0:a]atrim=0:60,asetpts=PTS-STARTPTS[a1];
[0:v]trim=60:180,setpts=(PTS-STARTPTS)/2[v2];[0:a]atrim=60:180,asetpts=PTS-STARTPTS,atempo=2[a2];
[0:v]trim=180,setpts=PTS-STARTPTS[v3];[0:a]atrim=180,asetpts=PTS-STARTPTS[a3];
[v1][a1][v2][a2][v3][a3]concat=n=3:v=1:a=1[v][a]" -map "[v]" -map "[a]" out.mp4
```
`atempo` accepts 0.5-100; chain for more (`atempo=2,atempo=2` = 4x). Mute fast sections
instead with `volume=0` if chipmunk audio is unwanted.

### 3. Crossfade between two clips
Both clips need the same resolution, fps and sample rate (run them through `assemble.py`
individually first if not). `offset` = duration of clip A minus the fade length.
```bash
ffmpeg -i a.mp4 -i b.mp4 -filter_complex \
"[0:v][1:v]xfade=transition=fade:duration=1:offset=9[v];[0:a][1:a]acrossfade=d=1[a]" \
-map "[v]" -map "[a]" out.mp4
```
Other transitions: `wipeleft`, `slideleft`, `circleopen`, `dissolve`, `fadeblack`.

### 4. Picture-in-picture (facecam bottom-right, 25% of a 1920-wide screen)
```bash
ffmpeg -i screen.mp4 -i cam.mp4 -filter_complex \
"[1:v]scale=480:-2[cam];[0:v][cam]overlay=W-w-40:H-h-40:shortest=1[v]" \
-map "[v]" -map 1:a out.mp4
```
Pick whichever input has the good mic for `-map N:a`.

### 5. Logo / watermark (top-right, 70% opacity)
```bash
ffmpeg -i in.mp4 -i logo.png -filter_complex \
"[1:v]scale=160:-1,format=rgba,colorchannelmixer=aa=0.7[l];[0:v][l]overlay=W-w-30:30" -c:a copy out.mp4
```

### 6. Zoom punch-in from 12s to 18s (1.3x, centered)
```bash
ffmpeg -i in.mp4 -vf "split[a][b];[b]crop=iw/1.3:ih/1.3,scale=1920:1080[z];[a][z]overlay=enable='between(t,12,18)'" -c:a copy out.mp4
```
Replace `1920:1080` with the input size.

### 7. Text callout / lower third (5-10 s)
Write the text to a file to avoid escaping problems:
```bash
printf 'Jane Doe - Network Engineer' > lt.txt
ffmpeg -i in.mp4 -vf "drawbox=x=60:y=ih-200:w=900:h=110:color=black@0.6:t=fill:enable='between(t,5,10)',\
drawtext=fontfile=/path/Font-Bold.ttf:textfile=lt.txt:expansion=none:fontsize=48:fontcolor=white:x=90:y=h-175:enable='between(t,5,10)'" \
-c:a copy out.mp4
```

### 8. Basic color
```bash
ffmpeg -i in.mp4 -vf "eq=brightness=0.04:contrast=1.08:saturation=1.15" -c:a copy out.mp4
ffmpeg -i in.mp4 -vf "lut3d=look.cube" -c:a copy out.mp4             # apply a .cube LUT
```

### 9. HDR (iPhone HLG / HDR10) to SDR
```bash
ffmpeg -i in.mov -vf "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p" out.mp4
```
If it fails with "no path between colorspaces", the file is missing color tags; state them
in the first zscale: `zscale=tin=arib-std-b67:pin=bt2020:min=bt2020nc:t=linear:npl=100`
(HLG, typical for iPhone) or `tin=smpte2084` (HDR10).
Needs ffmpeg built with zimg (`ffmpeg -filters | grep zscale`). If zscale is missing, use
`-vf "colorspace=all=bt709:iall=bt2020:fast=1"` (less accurate, still better than nothing).

### 10. Denoise voice / remove hum
```bash
ffmpeg -i in.mp4 -af "highpass=f=80,afftdn=nr=12:nf=-40,equalizer=f=50:t=q:w=2:g=-20" -c:v copy out.mp4
```
`afftdn` reduces steady background hiss/fan noise; keep `nr` at 20 or below to avoid robotic
artifacts. The equalizer notch targets 50 Hz mains hum (use 60 in the Americas).

### 11. Split a long recording into ~10-minute parts (no re-encode)
```bash
ffmpeg -i in.mp4 -c copy -f segment -segment_time 600 -reset_timestamps 1 part_%02d.mp4
```

### 12. Extract / replace audio
```bash
ffmpeg -i in.mp4 -vn -c:a pcm_s16le audio.wav                                 # extract
ffmpeg -i in.mp4 -i cleaned.wav -map 0:v -map 1:a -c:v copy -c:a aac -shortest out.mp4   # replace
```

### 13. GIF / short preview
```bash
ffmpeg -ss 1:00 -t 4 -i in.mp4 -vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" out.gif
```

### 14. Blur a region (e.g. an email address on screen, 3s-9s)
```bash
ffmpeg -i in.mp4 -filter_complex \
"[0:v]crop=400:60:800:500,gblur=sigma=12[b];[0:v][b]overlay=800:500:enable='between(t,3,9)'" -c:a copy out.mp4
```
`crop=w:h:x:y` - find coordinates by extracting a frame and viewing it.
