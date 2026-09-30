# Research: a motion-video skill that needs no installed software

September 2026. The question was whether Claude can make motion videos using a skill
alone, with no video software installed. Short answer: yes, but not with any of the
popular video skills. All of them depend on software that Claude's sandbox doesn't
have. This file records what was surveyed, what the sandbox actually provides, and
what was built and tested.

## 1. What the existing skills need

| Skill | What it does | Needs |
| --- | --- | --- |
| Remotion Agent Skills (`remotion-dev/skills`, official) | React components -> MP4. The most popular option by far | Node.js, npm, headless Chrome; Remotion's own renderer. Remotion has a company licence above a small team size |
| HyperFrames (HeyGen) and skills built on it | HTML/CSS -> MP4 | Node, headless Chrome, ffmpeg |
| Manim skills (e.g. Yusuke710, Math-To-Manim) | 3Blue1Brown-style maths animation | Cairo, pkg-config, ffmpeg, often LaTeX |
| digitalsamba claude-code-video-toolkit | full production suite | Remotion, ffmpeg, Playwright, ElevenLabs |
| ffmpeg skills (several) | transcode, trim, GIF | ffmpeg |
| character-animation-skill | sprite loops -> SVG/WebP/GIF | ImageMagick 7, ffmpeg, a Gemini API key |
| `anthropics/skills` slack-gif-creator (official) | Slack-sized GIFs with PIL | Pillow, numpy **and imageio**. Closest to zero-install, but GIF only, 128-480 px, and imageio is not in the documented sandbox library list |
| Animation-principles / motion-design text skills | guidance only | nothing, but they don't render |

The "awesome" lists (183+ repos in `awesome-claude-video-skills`) show the same
pattern: every skill that actually renders video calls out to Node + Chrome, to
ffmpeg, or to both.

## 2. What Claude's sandbox provides

From the code-execution tool documentation. claude.ai's file-creation sandbox is
the same kind of container, but its exact package list isn't published, so the
engine assumes only the Pillow + numpy baseline:

- Python 3.11 on x86-64 Linux, **1 CPU, 5 GiB RAM, 5 GiB disk**
- **No internet access**, so no `pip install` and no downloads at runtime
- Pre-installed: numpy, pandas, scipy, matplotlib, seaborn, **pillow**, reportlab
  with pycairo, python-pptx/docx, pypdf, and similar
- CLI tools: unzip, 7zip, ripgrep, fd, sqlite, bc. **No ffmpeg.** No
  imageio or imageio-ffmpeg, no opencv, no moviepy, and no Node.

So anything that shells out to ffmpeg or launches Chrome fails there. What *is*
available:

- Pillow writes animated **GIF, WebP and APNG** natively, with no external binary.
- A video container is just a documented byte layout. Photo-JPEG in QuickTime
  (`.mov`) and Motion-JPEG in AVI need no video codec, because each frame is a
  JPEG, which Pillow encodes. The container can be written in ~60 lines of
  `struct.pack`.
- H.264 cannot reasonably be encoded in pure Python on one CPU. That is the one
  hard limit.

## 3. Getting a real MP4 without software: the browser

Every modern browser has a hardware video encoder that JavaScript can use through
**WebCodecs**:

- `VideoEncoder` produces H.264 in Chrome/Edge (desktop + Android) and Safari,
  and VP9 in Chromium builds without proprietary codecs.
- WebCodecs doesn't write a file, only encoded chunks, so something has to mux
  them into MP4. Libraries exist (mediabunny, the successor to mp4-muxer), but a
  CDN dependency can be blocked by artifact sandboxes and offline use. A minimal
  single-track MP4 muxer (ftyp / mdat / moov with stts, stss, stsz, stco) is about
  60 lines, so the template writes its own.
- Fallback: `canvas.captureStream()` + `MediaRecorder` records WebM (or MP4 in
  Safari), but only in real time and not frame-exact.

So the skill has two routes. Route A runs in Claude's sandbox and writes
GIF/WebP/APNG/MOV/AVI. Route B is a self-contained HTML page that renders the same
kind of scene and exports an MP4 on the user's machine.

## 4. What was built and how it was tested

`scripts/motion.py`: easing library, springs, keyframes, stagger, wiggle; a
supersampled Pillow canvas (shapes, arcs, draw-on lines, text with tracking,
typewriter, rotation, images, layers with blur, shadow and glow, gradients,
vignette, grain); encoders for GIF (shared palette, so it doesn't flicker), WebP,
APNG, MOV and AVI, plus H.264 MP4 through ffmpeg when it happens to exist; frame
caching with a time budget so a long render can be resumed across tool calls; a
contact sheet and a numeric motion report for self-review.

`templates/browser_video.html`: the same timing helpers in JavaScript, a player
with scrubbing, WebCodecs export to H.264 MP4 with its own muxer, then
VP9-in-MP4, then real-time WebM fallback.

Tests run while building (ffmpeg 7.0 was installed separately, only as an
independent checker; the renderer ran with `MOTION_NO_FFMPEG=1` to match the
sandbox):

| Check | Result |
| --- | --- |
| `.mov` 1280x720, 180 frames | ffmpeg: `mjpeg (jpeg)`, 180 frames, 6.00 s, no errors |
| `.avi` 1280x720, 180 frames | ffmpeg: `mjpeg (MJPG)`, 180 frames, 6.00 s, no errors |
| `.gif` / `.webp` 640x360 | Chromium `ImageDecoder`: animated, 6.0 s (identical frames merged) |
| Transparent `.webp` / `.gif` / `.apng` | alpha 0..255 present / transparency index set / 100 frames |
| Resume: `time_budget=3`, same call repeated | finished in 4 calls, every frame rendered exactly once |
| Browser page, headless Chromium (no H.264 there) | VP9-in-MP4, 150 frames, 1920x1080, decodes cleanly, exported in 5.8 s |
| Browser muxer with real H.264 samples (x264) | decoded frames **bit-identical** to the source stream (framemd5 match) |
| H.264 path when ffmpeg exists | `h264 (High)`, correct frame count, streamed without buffering frames |

Bugs the self-review loop caught while building, which is why the workflow insists
on the contact sheet:

- Pillow *replaces* pixels when drawing a translucent colour onto an RGBA image
  instead of blending. A fading element became a black silhouette on its last
  frames. Fixed by drawing translucent and anti-aliased shapes on a scratch layer
  and alpha-compositing it.
- A drop-shadow helper faded the shadow but left the card itself fully opaque, so
  the card never left the screen.
- An element was drawn at frame 0 even though its entrance was at 1.0 s, because
  its opacity ignored its start time.
- Frames were JPEG 4:4:4, which some hardware and OS MJPEG decoders reject.
  Switched to 4:2:0.

Speed on one CPU is in the SKILL.md budget table: about 60 ms per frame at 360p and
about 500 ms at 1080p with 2x supersampling.

## 5. Limits worth telling users

- No H.264 from the sandbox itself. MP4 comes from the browser page or from a
  machine with ffmpeg.
- No audio.
- Pillow isn't a vector renderer. Smooth edges come from supersampling, which costs
  CPU. Bezier paths, blend modes and soft shadows on many objects are better in
  route B.
- Photo-JPEG `.mov` files are large (~10 MB for 6 s at 720p). They are
  intermediate-quality files meant for editors and upload, not for messaging.
  Lower `quality` (80) roughly halves the size.

## Sources

- Anthropic, code execution tool docs (sandbox specs, library list): https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- Anthropic skills repo, slack-gif-creator: https://github.com/anthropics/skills/blob/main/skills/slack-gif-creator/SKILL.md
- Remotion Agent Skills: https://github.com/remotion-dev/skills and https://www.remotion.dev/docs/ai/skills
- Claude Code Video Toolkit list: https://github.com/wilwaldon/Claude-Code-Video-Toolkit
- awesome-claude-video-skills: https://github.com/zhuyansen/awesome-claude-video-skills
- character-animation-skill: https://github.com/karem505/character-animation-skill
- motion-graphics skill packs: https://github.com/charlie947/motion-graphics-skills, https://github.com/haidrrrry/claude-remotion-skill
- mediabunny (WebCodecs muxing library, considered): https://github.com/Vanilagy/mediabunny
- MediaRecorder support notes: https://www.testmuai.com/learning-hub/mediarecorder-browser-support/
