import json
import os

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TOTAL_CHUNKS = 10
WIDTH, HEIGHT = 1280, 720


def build_cartoon_rigging_prompt(scene_text, duration, timeline=""):
  duration_ms = int(duration * 1000)
  return f"""
You are an expert 2D Vector Animator (Kurzgesagt / OverSimplified style). Build a self-contained HTML5 file (`<!DOCTYPE html>`) with dynamic, fast-paced multi-shot vector animation.

Narration: "{scene_text}"
Total Duration: {duration} seconds ({duration_ms} ms)
Timed Sequence:
{timeline}
Canvas Viewport: {WIDTH}x{HEIGHT} pixels

CRITICAL SCENE & SHOT RULES (AVOID STATIC SCENES):
1. MULTIPLE SHOTS PER CLIP (MANDATORY):
   - A single static background for {duration}s is UNACCEPTABLE.
   - NO HOST / MODERN PODCAST HEADS:
   - Absolutely NO modern studios, podcast microphones, hosts, headphones, Focus 100% on historical events, terrain, armies, maps, and metaphors.
   - Divide this clip into at least 3 to 4 DISTINCT visual shots using grouped layers:
     * `<g id="shot-1">...</g>` (e.g., Establishing wide scenery)
     * `<g id="shot-2">...</g>` (e.g., Close-up character action)
     * `<g id="shot-3">...</g>` (e.g., Infographic, map diagram, or battlefield cutaway)
   - In `window.updateSceneTime(t_ms)`, strictly toggle their visibility (`display: none/inline` or instant opacity 0/1) based on the Timed Sequence timestamps so the camera actually CUTS to new scenes every 4-8 seconds.

2. DETERMINISTIC DRIVER (RENDER HOOK):
   - Provide `window.updateSceneTime = function(t_ms) {{ ... }}`.
   - Strictly NO `requestAnimationFrame`, `setInterval`, `setTimeout`, `Date.now()`, or CSS `@keyframes`.
   - All limb movements, transitions, and scene cuts MUST be driven purely by `t_ms` (0 to {duration_ms}).

3. RIGGING & MOTION:
   - Dynamic character poses: characters must actually move, react, and gesture matching the narration line.
   - Limbs swing using simple sine waves driven by `t_ms` pivoted at the shoulder/hip joint.

4. VISUAL STYLE:
   - High-contrast, clean 2D vector art with bold outlines and expressive colors.
   - No substitle.
   - If needed short on-screen text labels (max 4 words: dates, locations, or names) timed to appear during relevant cues.

5. OUTPUT:
   - Output ONLY the standalone HTML code wrapped inside a single ```html ... ``` block. No explanations.
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
          f"[{current_pos:.1f}s - {a:.1f}s] Establishing visual environment and"
          " setup"
      )

    lines.append(f"[{a:.1f}s - {b:.1f}s] Action: {sg.text.strip()}")
    current_pos = max(current_pos, b)

  # Fill trailing gap
  if current_pos < chunk_duration - 0.3:
    lines.append(
        f"[{current_pos:.1f}s - {chunk_duration:.1f}s] Scene resolution and"
        " transition hold"
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
        or f"[0.0s - {duration:.1f}s] Action: {text}"
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
