import json
import os

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TOTAL_CHUNKS = 10
WIDTH, HEIGHT = 1280, 720


def build_cartoon_rigging_prompt(scene_text, duration, timeline=""):
  return f"""
You are a master 2D Vector Cartoon Animator (like Kurzgesagt / Oversimplified / Adobe Animate).
Build a complete, self-contained HTML5 document (`<!DOCTYPE html>`) that plays a rich, colorful 2D rigged cartoon animation for this historical narration:

Narration: "{scene_text}"
Target Duration: {duration} seconds
Timed narration (seconds from the start of this clip; this is exactly when each sentence is spoken):
{timeline}
Viewport Size: {WIDTH}x{HEIGHT} pixels

STRICT 2D CARTOON VISUAL & RIGGING RULES:
1. NO STICKMEN! Draw full-bodied, colorful 2D flat-vector cartoon characters using layered `<svg>` groups (`<g>`).
   - Every character MUST have: colored torso/tunic/armor (`<path>` or `<rect rx="...">`), expressive head with skin tone, eyes, eyebrows, headgear (crown, turban, helmet, hat), and separate articulated limbs (`<g class="arm-left">`, `<g class="arm-right">`, `<g class="leg-left">`, `<g class="leg-right">`) holding props (swords, shields, scrolls, muskets, flags).
2. DETERMINISTIC LIMB RIGGING (PURE MATH DRIVEN):
   - Rotate arms and legs around the shoulder/hip joint strictly driven by `t_ms` inside `window.updateSceneTime(t_ms)` using sine waves (e.g. `Math.sin(t_ms * 0.008) * 25`).
   - LIMB ATTACHMENT: Set local origin at joint (0, 0) or use absolute px transform-origin, making the top of limbs overlap into the torso so no gap is visible.
   - WALK CYCLE: Opposite limbs swing together in alternating phase with a subtle vertical body bob.
3. LAYERED PARALLAX ENVIRONMENT:
   - Rich multi-layered SVG background matching the era and culture: sky colors, distant silhouettes, midground architecture/landscape, and foreground terrain.
4. HTML5 CANVAS ATMOSPHERIC OVERLAY:
   - Include a transparent `<canvas>` overlay driven by `window.updateSceneTime(t_ms)` to draw dynamic particles (embers, dust, rain, smoke) so every frame is alive.
5. SYNCHRONIZED CLOCK HOOK (CRITICAL FOR RENDERER):
   - Define `window.updateSceneTime = function(t_ms) {{ ... }}` that updates ALL DOM transforms, limb angles, scene visibility, and `<canvas>` particles deterministically based on `t_ms` (0 to {int(duration*1000)} ms).
6. NEVER use `<use>` or `<symbol>`. Crowds and armies must be created at load time using a seeded deterministic JS loop and moved only from `window.updateSceneTime(t_ms)`.
7. CHARACTERS MUST STAND ON THE GROUND: Keep characters upright and translate them so feet touch terrain. No overlapping or floating.
8. TIMED NARRATION & ACTION BINDING (CRITICAL):
   - Total animation length is exactly {duration} seconds ({int(duration*1000)} ms).
   - The visual MUST directly act out what is spoken during each timed sentence in the cues above.
   - For every line:
     * When sentence t_start arrives in window.updateSceneTime(t_ms), trigger the specific action mentioned (e.g., if speech says "he signed the decree", show the character signing; if "the fleet set sail", animate ships moving).
     * Advance character poses/actions or switch scene groups (<g id="scene-N">) with a quick 0.3s cross-fade matching that exact time window.
9. DETERMINISTIC ONLY: Do NOT use requestAnimationFrame, setInterval, setTimeout, Date.now, performance.now, or CSS @keyframes. All visual changes must be a pure mathematical function of `t_ms`.
10. CAMERA: Pans and zooms must never expose canvas edges. Draw backgrounds wider than {WIDTH}x{HEIGHT}.
11. Short on-screen labels (dates, army sizes, names) are encouraged (max 4 words). Do not write full subtitles.
12. Output ONLY valid HTML inside a ```html ... ``` code block, with no explanation before or after.
""".strip()


def build_timeline(chunk_segments, chunk_start, chunk_duration):
  """Sentence lines with times strictly relative to chunk start, filling gaps."""
  lines = []
  current_pos = 0.0

  for sg in chunk_segments:
    a = max(round(sg.start - chunk_start, 1), 0.0)
    b = max(round(sg.end - chunk_start, 1), 0.0)

    # Fill leading silence/gap
    if a > current_pos + 0.3:
      lines.append(
          f"[{current_pos:.1f}s - {a:.1f}s] Establishing setting & visual"
          " setup"
      )

    lines.append(f"[{a:.1f}s - {b:.1f}s] {sg.text.strip()}")
    current_pos = max(current_pos, b)

  # Fill trailing gap
  if current_pos < chunk_duration - 0.3:
    lines.append(
        f"[{current_pos:.1f}s - {chunk_duration:.1f}s] Scene resolution & action"
        " wrap-up"
    )

  return "\n".join(lines)


def main():
  from faster_whisper import WhisperModel
  from pydub import AudioSegment

  os.makedirs(OUT, exist_ok=True)
  print(f"Loading {AUDIO_FILE} ...", flush=True)
  audio = AudioSegment.from_file(AUDIO_FILE)
  total = len(audio) / 1000.0

  print("Transcribing with Faster-Whisper ...", flush=True)
  model = WhisperModel("base", device="cpu", compute_type="int8")
  segments = list(model.transcribe(AUDIO_FILE)[0])

  if not segments:
    raise SystemExit("Whisper could not detect any speech in the audio.")

  # Dynamic target duration to keep all 10 chunks balanced
  chunks = []
  current_chunk = []
  chunk_start = 0.0

  for sg in segments:
    current_chunk.append(sg)
    chunk_elapsed = sg.end - chunk_start

    remaining_chunks = TOTAL_CHUNKS - len(chunks)
    if remaining_chunks > 1:
      dynamic_target = (total - chunk_start) / remaining_chunks
      if chunk_elapsed >= dynamic_target:
        chunks.append((chunk_start, sg.end, current_chunk))
        chunk_start = sg.end
        current_chunk = []

  if current_chunk:
    chunks.append((chunk_start, total, current_chunk))

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
        or f"[0.0s - {duration:.1f}s] {text}"
    )
    prompt = build_cartoon_rigging_prompt(text, duration, timeline)

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
