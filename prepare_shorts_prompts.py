import os
import json
import math
import subprocess
from faster_whisper import WhisperModel

AUDIO_FILE = "input_audio.mp3"
OUT_DIR = "prompts_output"
TARGET_CHUNK_SEC = 30.0
MAX_CHUNK_SEC = 35.0
MIN_CHUNK_SEC = 15.0

os.makedirs(OUT_DIR, exist_ok=True)


def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def cut_audio(src, dst, start, duration):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", src,
        "-acodec", "libmp3lame", "-b:a", "128k",
        dst
    ]
    subprocess.run(cmd, check=True)


def build_shorts_prompt(idx, total_chunks, duration, text, timeline):
    duration_ms = int(round(duration * 1000))
    min_shots = max(5, int(round(duration / 3.0)))

    return f"""You are an Elite 2D Vector Animator, Motion Graphics Director, and JavaScript Graphics Engineer specializing in viral 9:16 Vertical YouTube Shorts (Kurzgesagt / OverSimplified / Vox vertical motion style).

Create a COMPLETE, SELF-CONTAINED, SINGLE-FILE HTML5 animation (`scene_{idx}.html`) for a 9:16 YouTube Short.

======================================================================
1. STRICT TIMING & CLIP METADATA
======================================================================
- Clip Index: Part {idx + 1} of {total_chunks} (File: `scene_{idx}.html`)
- Exact Clip Duration: {duration:.2f} seconds ({duration_ms} ms)
- Aspect Ratio: 9:16 VERTICAL (YouTube Shorts / Reels / TikTok)
- Logical SVG Canvas: `width="720" height="1280" viewBox="0 0 720 1280"`
- Minimum Required Distinct Visual Shots: {min_shots} shots (change shots every ~2.5 to 3.5 seconds for high retention!)

Full Spoken Transcript for this Clip:
"{text}"

 Timestamped Sub-Segments (Local Clip Time 0.0s to {duration:.2f}s):
{timeline}

======================================================================
2. YOUTUBE SHORTS 9:16 VERTICAL SAFE-ZONE RULES (CRITICAL)
======================================================================
Because YouTube Shorts overlays UI buttons on the right and captions/channel info at the bottom, you MUST compose every shot inside these vertical coordinates (`720x1280`):
- TOP TITLE / HEADER ZONE (`Y: 110` to `Y: 260`, `X: 50` to `X: 670`): Place bold animated era headers, dates, location banners, and floating badges here.
- PRIMARY ACTION & CHARACTER STAGE (`Y: 280` to `Y: 960`, `X: 50` to `X: 610`): Place all main characters, buildings, maps, battles, and key visual storytelling here. Keep `X: 610` to `720` free of crucial text/faces (right-side UI buttons).
- LOWER ENVIRONMENT / GROUND ZONE (`Y: 960` to `Y: 1280`): Use for ground terrain, foreground props, waves, roads, or atmospheric shadows. NEVER place important text below `Y: 1000`.
- CAMERA TRANSFORM CENTER: Always use `(360, 640)` as the center pivot for camera zoom/pan transforms (e.g., `translate(360, 640) scale(...) translate(-360, -640)`).

======================================================================
3. VISUAL STYLE & ANIMATION ENGINE REQUIREMENTS
======================================================================
- Multi-Layered Vector Art: Every shot must include sky/backdrop gradients, parallax background, mid-ground architecture/terrain, detailed rigged characters (head, eyes with blink, mouth with lip-sync, torso, articulated left/right arms & legs), foreground elements, and bold kinetic typography titles.
- Continuous Motion: Nothing may ever freeze! Use `Math.sin` / `Math.cos`, `easeOutCubic`, `easeOutBack`, `lerp`, and `clamp` for smooth camera zoom/pan, character walking/gesturing, waving flags, drifting clouds, and glowing particles.
- Deterministic Time Control:
  - Expose `window.updateSceneTime = function(ms) {{ ... }};` where `ms` runs from `0` to `{duration_ms}`.
  - Also run a standard `requestAnimationFrame` loop for normal browser preview, which automatically pauses when `window.updateSceneTime` is called externally by the headless renderer.
  - Initialize at `window.updateSceneTime(0);` on load.

======================================================================
4. OUTPUT FORMAT
======================================================================
Return ONLY the raw, complete, valid HTML5 code starting with `<!DOCTYPE html>` and ending with `</html>`. Do NOT wrap in markdown explanations or truncate any section."""


def main():
    if not os.path.exists(AUDIO_FILE):
        raise SystemExit(f"Missing {AUDIO_FILE}")

    total_dur = get_audio_duration(AUDIO_FILE)
    print(f"Loading {AUDIO_FILE} ({total_dur:.2f}s)...", flush=True)

    print("Transcribing with Faster-Whisper...", flush=True)
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_gen, _ = model.transcribe(AUDIO_FILE, word_timestamps=True)
    segments = list(segments_gen)

    chunks = []
    cur_segs = []
    chunk_start = 0.0

    for seg in segments:
        if not cur_segs:
            cur_segs.append(seg)
            continue

        cur_dur = seg.end - chunk_start
        if cur_dur >= TARGET_CHUNK_SEC or (seg.end - chunk_start) >= MAX_CHUNK_SEC:
            chunks.append((chunk_start, cur_segs[-1].end, cur_segs))
            chunk_start = cur_segs[-1].end
            cur_segs = [seg]
        else:
            cur_segs.append(seg)

    if cur_segs:
        if chunks and (total_dur - chunk_start) < MIN_CHUNK_SEC:
            prev_s, _, prev_segs = chunks.pop()
            prev_segs.extend(cur_segs)
            chunks.append((prev_s, total_dur, prev_segs))
        else:
            chunks.append((chunk_start, total_dur, cur_segs))

    if not chunks:
        chunks = [(0.0, total_dur, [])]

    chunks_meta = []
    all_prompts_blocks = []

    for idx, (c_start, c_end, c_segs) in enumerate(chunks):
        dur = round(c_end - c_start, 2)
        audio_out = os.path.join(OUT_DIR, f"audio_{idx}.mp3")
        cut_audio(AUDIO_FILE, audio_out, c_start, dur)

        texts = []
        tl_lines = []
        for s in c_segs:
            ls = max(0.0, round(s.start - c_start, 1))
            le = min(dur, round(s.end - c_start, 1))
            clean_t = s.text.strip()
            if clean_t:
                texts.append(clean_t)
                tl_lines.append(f"[{ls:.1f}s - {le:.1f}s] Narration & Action: {clean_t}")

        full_text = " ".join(texts) if texts else "Visual sequence."
        timeline_str = "\n".join(tl_lines) if tl_lines else f"[0.0s - {dur:.1f}s] Visual sequence."

        prompt_txt = build_shorts_prompt(idx, len(chunks), dur, full_text, timeline_str)
        prompt_path = os.path.join(OUT_DIR, f"prompt_{idx}.txt")
        with open(prompt_path, "w", encoding="utf-8") as pf:
            pf.write(prompt_txt)

        all_prompts_blocks.append(f"===== PROMPT {idx} =====\n{prompt_txt}")
        chunks_meta.append({
            "index": idx,
            "duration": dur,
            "aspect_ratio": "9:16",
            "width": 720,
            "height": 1280,
            "text": full_text,
            "timeline": timeline_str
        })
        print(f"Chunk {idx}: {dur:.1f}s | {full_text[:65]}...", flush=True)

    with open(os.path.join(OUT_DIR, "chunks.json"), "w", encoding="utf-8") as jf:
        json.dump(chunks_meta, jf, indent=2, ensure_ascii=False)

    with open(os.path.join(OUT_DIR, "all_prompts.txt"), "w", encoding="utf-8") as af:
        af.write("\n\n".join(all_prompts_blocks))

    print(f"Done: {OUT_DIR}/ ({len(chunks)} vertical 9:16 chunks created)", flush=True)


if __name__ == "__main__":
    main()
