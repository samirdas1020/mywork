import json
import os

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TARGET_CHUNK_SEC = 30.0
WIDTH, HEIGHT = 720, 1280  # 9:16 Vertical Shorts format


def build_cartoon_rigging_prompt(
    scene_text, duration, timeline="", speech_windows=None, chunk_idx=0
):
  duration_ms = int(duration * 1000)
  min_shots = max(8, int(round(duration / 3.0)))
  speech_windows = speech_windows or []

  return f"""
You are an elite 2D Vector Animation & Film Director (OverSimplified / Kurzgesagt / LEMMiNO studio quality). Build a complete, self-contained HTML5 file (`<!DOCTYPE html>`) with deeply cinematic, fast-paced, multi-shot 9:16 VERTICAL vector animation engineered for maximum viewer retention on YouTube Shorts.

Clip Index: Part {chunk_idx + 1}
Narration: "{scene_text}"
Total Duration: {duration} seconds ({duration_ms} ms)
Active Speech Windows (ms): {json.dumps(speech_windows)}
Timed Visual & Action Sequence:
{timeline}
Canvas Coordinate System: {WIDTH}x{HEIGHT} (9:16 Vertical Full-Screen SVG)

CRITICAL CINEMATIC DIRECTION & STUDIO RULES:
1. NO SLIDESHOWS — TRUE SPATIAL TRAVEL, CAMERA & PARALLAX DEPTH:
   - A static scene, center-locked zoom, or simple slideshow cut is UNACCEPTABLE. Every single shot MUST feel like a real film camera moving through space and depth.
   - Build `.bg-layer` and `.mid-layer` wider/taller than `{WIDTH}x{HEIGHT}` (e.g., spanning X from `-500` to `+1500` or Y from `-400` to `+1700`) so the camera can genuinely travel, pan, and track across space rather than merely zooming in place.
   - Inside EACH shot `<g id="shot-N">`, structure artwork into 3 distinct depth layers (`class="bg-layer"`, `class="mid-layer"`, `class="fg-layer"`).
   - In `window.updateSceneTime(t_ms)`, calculate normalized shot progress `p` (from `0.0` to `1.0` within that shot's active window) and apply continuous eased camera transforms (`translate`, `scale`, and subtle `rotate`) with wide spatial travel (`startX, startY -> endX, endY`) plus moving subjects/vehicles/characters crossing the frame.
   - Apply parallax depth across all layers: shift `bg-layer` at `0.3x` speed, `mid-layer` at `1.0x` speed, and `fg-layer` (passing pillars, trees, wires, window frames, smoke, sparks) at `1.6x` speed so the viewer feels forward movement and travel.
   - Add impact camera shake (`Math.sin(t_ms * 0.12) * 7`) during explosions, battle clashes, slams, or dramatic reveals.

2. ULTRA-FAST MULTI-SHOT PACING & FILM GRAMMAR (EVERY ~3 SECONDS):
   - Divide this {duration}s clip into AT LEAST {min_shots} DISTINCT visual shots inside a single `<svg viewBox="0 0 {WIDTH} {HEIGHT}" style="width:100vw; height:100vh; display:block;">`:
     * `<g id="shot-1">...</g>`, `<g id="shot-2">...</g>`, up to `<g id="shot-{min_shots}">...</g>`
   - **MANDATORY OPENING HOOK (`shot-1`, 0ms to 2500ms):** Start mid-action with high visual tension—a sudden dramatic push-in or tracking shot into an intense face, cannon fire, glowing tactical map invasion, or mysterious artifact. Never start with a slow empty landscape.
   - Avoid putting every focal subject dead-center at `(360, 620)`. Alternate framing dynamically across consecutive shots using rule-of-thirds placement (left/right third, high/low horizon), Dutch angles, sweeping map/landscape pans, over-the-shoulder confrontations, and depth push-ins past foreground framing elements.
   - Vary shot motion and camera scale direction across consecutive shots (e.g., lateral tracking pan -> deep push-in through foreground -> wide pull-back/pan) instead of repeating identical center-zooms.

3. FULL-FRAME 9:16 COMPOSITION & EDGE FLOW:
   - Use the full {WIDTH}x{HEIGHT} vertical frame naturally as the camera travels across the wider world—do NOT crop or squeeze the scene into a narrow center box that cuts off surrounding context, maps, or side elements.
   - Allow characters, vehicles, and props to enter from and exit past the frame edges naturally during pans and tracking shots, while keeping primary faces and key focal action readable within the main visible viewport.

4. EXPRESSIVE CHARACTER RIGGING & LIP-SYNC (NO STICK FIGURES):
   - Build rich OverSimplified/Kurzgesagt characters using layered `<path>` elements, gradients, directional rim lighting, cast shadows, and bold `3px-4px` dark outlines (`#1a1a2e`):
     * Detailed historical headgear, crowns, uniforms, armor, and period props.
     * Expressive faces: angled eyebrows for anger/shock, periodic blinking, and animated mouth/jaw opening/closing rhythmically using `Math.abs(Math.sin(t_ms * 0.028))` ONLY when `t_ms` falls inside `Active Speech Windows` (keep mouth closed during silent pauses).
     * Hierarchical limb rigging pivoted at shoulders and hips using `transform-origin` and sine waves driven by `t_ms`, plus secondary/follow-through motion where appropriate.

5. CINEMATIC LIGHTING, PURE VISUAL STORYTELLING & NO SUBTITLES:
   - Motivate lighting in each shot with a clear light source direction, shadow contrast, dramatic `<linearGradient>`, `<radialGradient>`, vignette overlays, glowing highlights, and drop shadows for film-like depth.
   - Every shot MUST tell the story through animated characters, objects, maps, lighting shifts, and physical cause-and-effect—NEVER rely on large text, counters, or title cards as the main visual of a shot.
   - Every shot must contain at least TWO distinct in-scene animations (e.g., character gesture/limb/head motion + moving vehicles/projectiles/smoke/light beams/map shifts) in addition to camera travel and 3-layer parallax.
   - **STRICTLY NO SUBTITLES OR CAPTIONS.** Outside of map shots (see Rule 8), keep on-screen labels minimal (1-2 words or a year) and secondary to the main action, placed naturally within the visible viewport without clipping or covering key faces.

6. SEAMLESS LOOP TRANSITION:
   - In the final 1.5 seconds (`{max(0, duration_ms - 1500)}ms` to `{duration_ms}ms`), execute a rapid whip-zoom into darkness or a focal element that visually matches `shot-1` for seamless looping.

7. DETERMINISTIC RENDER HOOK (STRICT):
   - CSS must set `html, body {{ margin: 0; padding: 0; overflow: hidden; background: #0d1117; }}`.
   - Provide `window.updateSceneTime = function(t_ms) {{ ... }}` and call `window.updateSceneTime(0);` at load.
   - Strictly NO `requestAnimationFrame`, `setInterval`, `setTimeout`, `Date.now()`, or CSS `@keyframes`.
   - Every movement, parallax shift, camera zoom/pan, mouth movement, and shot cut MUST be a pure mathematical function of `t_ms` (0 to {duration_ms}).

8. MAP ANIMATION SYSTEM (for geography, war, empire & territory shots):
   - Use map shots whenever the narration involves places, borders, invasions, or expansion. Alternate map shots with character/scene shots.
   - Draw a simple stylized map (landmasses, coastlines, rivers, mountains) wider than the canvas so the camera can pan and travel across it.
   - TERRITORY: each realm is a `<path>` region; animate color fade and border growth/shrink as a function of `t_ms` to show conquest or expansion.
   - ARMIES: small flag/icon markers that move along a path (`getPointAtLength`) driven by `t_ms`. Show battles with a short flash/clash effect at the meeting point.
   - ARROWS: draw advance arrows with `stroke-dashoffset` tied to `t_ms`, with an arrowhead at the tip.
   - LABELS: on map shots, place names and years may appear with a quick fade-in near their location (1-3 words), then fade out. Keep them inside the visible viewport and never over key action.
   - Keep the same map shape, realm colors, and army colors consistent across the whole clip.

9. OUTPUT:
   - Output ONLY the standalone HTML code wrapped inside a single ```html ... ``` block. No explanations.
""".strip()


def is_sentence_end(text):
  t = text.strip()
  return bool(t) and t[-1] in {".", "!", "?", "…"}


def build_timeline(chunk_segments, chunk_start, chunk_duration):
  """Sentence lines with fast-paced hook, travel cues, and active speech windows."""
  lines = []
  speech_windows = []
  current_pos = 0.0

  for i, sg in enumerate(chunk_segments):
    a = max(round(sg.start - chunk_start, 1), 0.0)
    b = min(max(round(sg.end - chunk_start, 1), a), round(chunk_duration, 1))
    if b > a:
      speech_windows.append([int(a * 1000), int(b * 1000)])

    if a > current_pos + 0.2:
      cue_type = (
          "HIGH-IMPACT OPENING HOOK (Tracking / Sudden Zoom)"
          if current_pos == 0.0
          else "Fast Cut, Spatial Pan & Camera Punch-In"
      )
      lines.append(f"[{current_pos:.1f}s - {a:.1f}s] {cue_type}")

    prefix = (
        "OPENING HOOK & Narration"
        if i == 0
        else (
            "Climax / Payoff & Narration"
            if i == len(chunk_segments) - 1
            else "Travel Action & Narration"
        )
    )
    lines.append(f"[{a:.1f}s - {b:.1f}s] {prefix}: {sg.text.strip()}")
    current_pos = max(current_pos, b)

  if current_pos < chunk_duration - 0.2:
    lines.append(
        f"[{current_pos:.1f}s - {chunk_duration:.1f}s] Cliffhanger Zoom & Loop"
        " Transition"
    )

  return "\n".join(lines), speech_windows


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
      reached_target = chunk_elapsed >= dynamic_target
      hard_cap = chunk_elapsed >= (dynamic_target + 6.0)
      clean_boundary = is_sentence_end(sg.text) or hard_cap

      if reached_target and clean_boundary and (total - sg.end) >= 3.0:
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

    timeline, speech_windows = build_timeline(chunk_segs, start, duration)
    if not timeline:
      timeline = f"[0.0s - {duration:.1f}s] OPENING HOOK & Action: {text}"

    prompt = build_cartoon_rigging_prompt(
        text,
        duration,
        timeline=timeline,
        speech_windows=speech_windows,
        chunk_idx=i,
    )

    with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
      f.write(prompt)
    combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

    meta.append({
        "index": i,
        "duration": duration,
        "text": text,
        "speech_windows_ms": speech_windows,
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
