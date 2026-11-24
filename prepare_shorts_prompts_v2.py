import json
import os

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TARGET_CHUNK_SEC = 30.0
WIDTH, HEIGHT = 720, 1280  # 9:16 Vertical Shorts format


def build_cartoon_rigging_prompt(
    scene_text, duration, timeline="", chunk_idx=0
):
  duration_ms = int(duration * 1000)
  min_shots = max(12, int(round(duration / 2.2)))

  return f"""
You are an elite 2D Vector Animation Director (OverSimplified / Kurzgesagt / LEMMiNO studio quality). Build a complete, self-contained HTML5 file (`<!DOCTYPE html>`) with deeply cinematic, fast-paced, multi-shot 9:16 VERTICAL vector animation engineered for maximum viewer retention on YouTube Shorts.

Clip Index: Part {chunk_idx + 1}
Narration: "{scene_text}"
Total Duration: {duration} seconds ({duration_ms} ms)
Timed Visual & Action Sequence:
{timeline}
Canvas Coordinate System: {WIDTH}x{HEIGHT} (9:16 Vertical Full-Screen SVG)

CRITICAL CINEMATIC DIRECTION & STUDIO RULES:
1. NO SLIDESHOWS — TRUE CINEMATIC CAMERA & PARALLAX DEPTH:
   - A static scene or simple slideshow cut is UNACCEPTABLE. Every single shot MUST feel like a real camera moving through a 3D world.
   - Inside EACH shot `<g id="shot-N">`, structure artwork into 3 distinct depth layers (`class="bg-layer"`, `class="mid-layer"`, `class="fg-layer"`).
   - In `window.updateSceneTime(t_ms)`, calculate normalized shot progress `p` (from `0.0` to `1.0` within that shot's active window) and apply continuous mathematical camera transforms (`translate` and `scale`) so the camera continuously pushes in, zooms out, or pans across the scene.
   - Apply parallax depth across all layers: shift `bg-layer` at `0.3x` speed, `mid-layer` at `1.0x` speed, and `fg-layer` (silhouettes, smoke, sparks, foreground pillars) at `1.6x` speed.
   - Add impact camera shake (`Math.sin(t_ms * 0.12) * 7`) during explosions, battle clashes, or dramatic reveals.

2. ULTRA-FAST MULTI-SHOT PACING (EVERY 2 SECONDS):
   - Divide this {duration}s clip into AT LEAST {min_shots} DISTINCT visual shots inside a single `<svg viewBox="0 0 {WIDTH} {HEIGHT}" style="width:100vw; height:100vh; display:block;">`:
     * `<g id="shot-1">...</g>`, `<g id="shot-2">...</g>`, up to `<g id="shot-{min_shots}">...</g>`
   - **MANDATORY 2-SECOND OPENING HOOK (`shot-1`, 0ms to 2500ms):** Start mid-action with high visual tension—a sudden dramatic zoom into an intense face, cannon fire, glowing tactical map invasion, or mysterious artifact. Never start with a slow empty landscape.
   - Alternate framing dynamically between extreme Dutch-angles, sweeping aerial map pans, over-the-shoulder character confrontations, and wide establishing environments.

3. VERTICAL FRAMING (9:16 SAFE ZONE):
   - Keep focal points, faces, and key action centered between X: 60 to 600 and Y: 200 to 980 so YouTube Shorts UI icons never obstruct important visuals.

4. EXPRESSIVE CHARACTER RIGGING & LIP-SYNC (NO STICK FIGURES):
   - Build rich OverSimplified/Kurzgesagt characters using layered `<path>` elements, gradients, rim lighting, and bold `3px-4px` dark outlines (`#1a1a2e`):
     * Detailed historical headgear, crowns, uniforms, armor, and period props.
     * Expressive faces: angled eyebrows for anger/shock, periodic blinking, and animated mouth/jaw opening/closing rhythmically using `Math.abs(Math.sin(t_ms * 0.028))` during active Narration timestamps.
     * Hierarchical limb rigging pivoted at shoulders and hips using `transform-origin` and sine waves driven by `t_ms`.

5. CINEMATIC LIGHTING, TYPOGRAPHY & NO SUBTITLES:
   - Use dramatic `<linearGradient>`, `<radialGradient>`, vignette overlays, glowing highlights, and drop shadows for atmospheric depth.
   - **STRICTLY NO SUBTITLES OR CAPTIONS.** Use only bold cinematic on-screen titles/labels (max 3-4 words for key dates, locations, or troop numbers) integrated into the scene perspective.

6. SEAMLESS LOOP TRANSITION:
   - In the final 1.5 seconds (`{duration_ms - 1500}ms` to `{duration_ms}ms`), execute a rapid whip-zoom into darkness or a focal element that visually matches `shot-1` for seamless looping.

7. DETERMINISTIC RENDER HOOK (STRICT):
   - CSS must set `html, body {{ margin: 0; padding: 0; overflow: hidden; background: #0d1117; }}`.
   - Provide `window.updateSceneTime = function(t_ms) {{ ... }}` and call `window.updateSceneTime(0);` at load.
   - Strictly NO `requestAnimationFrame`, `setInterval`, `setTimeout`, `Date.now()`, or CSS `@keyframes`.
   - Every movement, parallax shift, camera zoom, mouth movement, and shot cut MUST be a pure mathematical function of `t_ms` (0 to {duration_ms}).

8. OUTPUT:
   - Output ONLY the standalone HTML code wrapped inside a single ```html ... ``` block. No explanations.
""".strip()


def build_timeline(chunk_segments, chunk_start, chunk_duration):
  """Sentence lines with fast-paced hook and action cues."""
  lines = []
  current_pos = 0.0

  for i, sg in enumerate(chunk_segments):
    a = max(round(sg.start - chunk_start, 1), 0.0)
    b = min(max(round(sg.end - chunk_start, 1), 0.0), round(chunk_duration, 1))

    if a > current_pos + 0.2:
      cue_type = (
          "HIGH-IMPACT OPENING HOOK (Sudden Zoom/Conflict)"
          if current_pos == 0.0
          else "Fast Cut & Camera Punch-In"
      )
      lines.append(f"[{current_pos:.1f}s - {a:.1f}s] {cue_type}")

    prefix = (
        "OPENING HOOK & Narration" if i == 0 else "Fast Action & Narration"
    )
    lines.append(f"[{a:.1f}s - {b:.1f}s] {prefix}: {sg.text.strip()}")
    current_pos = max(current_pos, b)

  if current_pos < chunk_duration - 0.2:
    lines.append(
        f"[{current_pos:.1f}s - {chunk_duration:.1f}s] Cliffhanger Zoom & Loop"
        " Transition"
    )

  return "\n".join(lines)


def main():
  from faster_whisper import WhisperModel
  from pydub import AudioSegment

  os.makedirs(OUT, exist_ok=True)
  print(f"Loading {AUDIO_FILE} ...", flush=True)
  audio = AudioSegment.from_file(AUDIO_FILE)
  total = len(audio) / 1000.0

  target_chunks = max(1, round(total / TARGET_CHUNK_SEC))

  print("Transcribing with Faster-Whisper ...", flush=True)
  model = WhisperModel("base", device="cpu", compute_type="int8")
  segments = list(model.transcribe(AUDIO_FILE)[0])

  if not segments:
    raise SystemExit("Whisper could not detect any speech in the audio.")

  chunks = []
  current_chunk = []
  chunk_start = 0.0

  for sg in segments:
    current_chunk.append(sg)
    chunk_elapsed = sg.end - chunk_start

    remaining_chunks = target_chunks - len(chunks)
    if remaining_chunks > 1:
      dynamic_target = (total - chunk_start) / remaining_chunks
      if chunk_elapsed >= dynamic_target and (total - sg.end) >= 3.0:
        chunks.append((chunk_start, sg.end, current_chunk))
        chunk_start = sg.end
        current_chunk = []

  if current_chunk:
    chunks.append((chunk_start, total, current_chunk))
  elif chunks:
    prev_start, _, prev_segs = chunks[-1]
    chunks[-1] = (prev_start, total, prev_segs)

  meta, combined = [], []
  for i, (start, end, chunk_segs) in enumerate(chunks):
    duration = round(max(end - start, 2.0), 2)
    text = (
        " ".join(s.text.strip() for s in chunk_segs).strip()
        or f"Historical Scene {i+1}"
    )

    audio[int(start * 1000) : int(end * 1000)].export(
        f"{OUT}/audio_{i}.mp3", format="mp3"
    )

    timeline = (
        build_timeline(chunk_segs, start, duration)
        or f"[0.0s - {duration:.1f}s] OPENING HOOK & Action: {text}"
    )
    prompt = build_cartoon_rigging_prompt(text, duration, timeline, chunk_idx=i)

    with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
      f.write(prompt)
    combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

    meta.append({
        "index": i,
        "duration": duration,
        "text": text,
        "timeline": timeline,
    })
    print(f"Chunk {i}: {duration:.1f}s | {text[:60]}...", flush=True)

  with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(combined))
  with open(f"{OUT}/chunks.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

  print(f"Done: {OUT}/ ({len(chunks)} chunks created)", flush=True)


if __name__ == "__main__":
  main()
