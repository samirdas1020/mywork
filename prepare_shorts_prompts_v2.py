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
  # প্রতি ২.২ সেকেন্ডে অন্তত ১টি করে নতুন শট বা বড় ভিজ্যুয়াল পরিবর্তন
  min_shots = max(12, int(round(duration / 2.2)))

  return f"""
You are an elite 2D Vector Animation Director (OverSimplified / Kurzgesagt studio quality). Build a complete, self-contained HTML5 file (`<!DOCTYPE html>`) with ultra-fast-paced, cinematic multi-shot 9:16 VERTICAL vector animation engineered specifically for high retention on YouTube Shorts.

Clip Index: Part {chunk_idx + 1}
Narration: "{scene_text}"
Total Duration: {duration} seconds ({duration_ms} ms)
Timed Visual & Action Sequence:
{timeline}
Canvas Coordinate System: {WIDTH}x{HEIGHT} (9:16 Vertical Full-Screen SVG)

CRITICAL VIRAL RETENTION & STUDIO QUALITY RULES:
1. ULTRA-FAST MULTI-SHOT PACING (EVERY 2 SECONDS):
   - Retention is everything. NEVER hold a static angle for more than 2.5 seconds. NO modern studios, podcast mics, hosts, or talking heads. Focus 100% on historical environments, armies, architecture, tactical maps, and visual metaphors.
   - Divide this {duration}s clip into AT LEAST {min_shots} DISTINCT visual shots inside a single `<svg viewBox="0 0 {WIDTH} {HEIGHT}" style="width:100vw; height:100vh; display:block;">`:
     * `<g id="shot-1">...</g>`, `<g id="shot-2">...</g>`, up to `<g id="shot-{min_shots}">...</g>`
   - **MANDATORY 2-SECOND OPENING HOOK (`shot-1`, 0ms to 2500ms):** Start immediately with high-stakes visual action—an explosion, dramatic zoom-in on a shocked/angry character, an advancing army arrow on a map, or a visual mystery. NEVER start with a slow empty landscape.
   - Alternate shot types rapidly:
     * Extreme close-up of intense character emotion or symbolic artifact
     * Tactical war-room map with animated glowing territory arrows & borders
     * Medium dramatic character confrontation or battle clash
     * Wide establishing environment with 3-layer parallax
   - In `window.updateSceneTime(t_ms)`, strictly cut between shots (`display: none` vs `inline`) every 2.0–2.5 seconds synced to the Timed Sequence.

2. VERTICAL FRAMING, CAMERA SHAKE & CONTINUOUS MOTION (9:16 SAFE ZONE):
   - Keep main characters and action centered between X: 60 to 600 and Y: 200 to 980 so YouTube Shorts UI buttons never cover important details.
   - Apply continuous camera motion to EVERY active shot using `t_ms`: punch-in zooms (`scale(1.0)` to `scale(1.12)`), vertical/horizontal pans, and camera shake (`Math.sin(t_ms * 0.1) * 6`) during impacts or dramatic reveals.
   - Include ambient motion in every shot: drifting smoke/clouds, waving flags, flickering fire, or marching silhouettes.

3. EXPRESSIVE CHARACTER RIGGING & LIP-SYNC (NO STICK FIGURES):
   - Build expressive OverSimplified/Kurzgesagt characters using layered `<path>` and `<g>` elements with bold `3px-4px` dark outlines (`#1a1a2e`):
     * Detailed historical helmets, crowns, uniforms, armor, and props (swords, maps, cannons, scrolls).
     * Expressive faces: angled eyebrows for anger/shock, periodic blinking, and animated mouth/jaw opening/closing rhythmically using `Math.abs(Math.sin(t_ms * 0.028))` during active Narration timestamps.
     * Hierarchical limb rigging pivoted at shoulders and hips using `transform-origin` and sine waves driven by `t_ms`.

4. VISUAL POLISH, TYPOGRAPHY & NO SUBTITLES:
   - Rich color palettes with `<linearGradient>`, `<radialGradient>`, drop shadows, and crisp vector shading.
   - **STRICTLY NO SUBTITLES OR CAPTIONS.** Use only bold cinematic on-screen titles/labels (max 3-4 words: dates, locations, troop numbers like "1513 AD" or "50,000 TROOPS") when key visual cues hit.

5. SEAMLESS LOOP ENDING:
   - In the final 1.5 seconds (`{duration_ms - 1500}ms` to `{duration_ms}ms`), apply a dramatic whip-zoom or visual transition that matches the energy of `shot-1` to encourage seamless looping.

6. DETERMINISTIC RENDER HOOK (STRICT):
   - CSS must set `html, body {{ margin: 0; padding: 0; overflow: hidden; background: #0d1117; }}`.
   - Provide `window.updateSceneTime = function(t_ms) {{ ... }}` and call `window.updateSceneTime(0);` at load.
   - Strictly NO `requestAnimationFrame`, `setInterval`, `setTimeout`, `Date.now()`, or CSS `@keyframes`.
   - Every movement, camera pan, mouth movement, and shot cut MUST be a pure mathematical function of `t_ms` (0 to {duration_ms}).

7. OUTPUT:
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
