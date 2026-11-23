with open("prepare_shorts_prompts_test.py", "w", encoding="utf-8") as f1:
    f1.write("""import json
import os
import requests

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TARGET_CHUNK_SEC = 30.0
WIDTH, HEIGHT = 720, 1280

def build_cartoon_rigging_prompt(scene_text, duration, timeline="", chunk_idx=0):
  duration_ms = int(duration * 1000)
  min_shots = max(4, int(round(duration / 5.0)))

  return f'''
You are an elite 2D Vector Animation Director (OverSimplified / Kurzgesagt studio quality). Build a complete, self-contained HTML5 file (`<!DOCTYPE html>`) with rich, cinematic, fast-paced multi-shot 9:16 VERTICAL vector animation for YouTube Shorts.

Clip Index: Part {chunk_idx + 1}
Narration: "{scene_text}"
Total Duration: {duration} seconds ({duration_ms} ms)
Timed Sequence:
{timeline}
Canvas Coordinate System: {WIDTH}x{HEIGHT} (9:16 Vertical Full-Screen SVG)

CRITICAL STUDIO QUALITY & SHOT RULES:
1. HIGH-PACE MULTI-SHOT DIRECTION (MANDATORY):
   - A static scene is UNACCEPTABLE. NO modern studios, podcast mics, hosts, or talking heads. Focus 100% on historical environments, armies, architecture, tactical maps, and visual metaphors.
   - Divide this {duration}s clip into AT LEAST {min_shots} DISTINCT visual shots inside a single `<svg viewBox="0 0 {WIDTH} {HEIGHT}" style="width:100vw; height:100vh; display:block;">`:
     * `<g id="shot-1">...</g>`, `<g id="shot-2">...</g>`, up to `<g id="shot-{min_shots}">...</g>`
   - Alternate shot types for cinematic variety:
     * Wide establishing environment with 3-layer parallax (sky/gradients, mid-ground terrain/buildings, foreground props)
     * Medium dramatic character confrontation or action
     * Tactical war-room map / animated territory arrows / data visual metaphor
     * Extreme close-up showing intense character emotion or symbolic object
   - In `window.updateSceneTime(t_ms)`, strictly cut between shots (`display: none` vs `inline`) synced to the Timed Sequence so the scene changes every 4-5 seconds.

2. VERTICAL FRAMING & VIRTUAL CAMERA (9:16 SAFE ZONE):
   - Compose scenes vertically (`720x1280`): keep main characters and titles centered between X: 60 to 600 and Y: 200 to 980 so YouTube Shorts UI buttons never cover important details.
   - Even while a shot is active, apply continuous slow camera motion (slow zoom-in, vertical/horizontal pan, or dramatic shake during impacts) by updating `<g>` transforms using `t_ms`.
   - Include ambient motion in every shot: drifting clouds/smoke, waving banners, flickering torches, or marching silhouettes.

3. ADVANCED CHARACTER RIGGING & LIP-SYNC (NO STICK FIGURES):
   - NEVER draw simple stick figures or basic circles. Build expressive OverSimplified/Kurzgesagt characters using layered `<path>` and `<g>` elements:
     * Detailed period headgear/helmets, clothing folds, tunics, armor, and props (swords, scrolls, muskets).
     * Expressive faces: distinct eyebrows that angle for anger/shock, eyes that blink periodically, and an animated mouth/jaw group that opens/closes rhythmically using `Math.abs(Math.sin(t_ms * 0.025))` during active Narration timestamps.
     * Hierarchical limb rigging pivoted at shoulders (`transform-origin`) and hips, swinging naturally with sine waves driven by `t_ms`.

4. DETERMINISTIC RENDER HOOK (STRICT):
   - CSS must set `html, body {{ margin: 0; padding: 0; overflow: hidden; background: #0d1117; }}`.
   - Provide `window.updateSceneTime = function(t_ms) {{ ... }}` and call `window.updateSceneTime(0);` at load.
   - Strictly NO `requestAnimationFrame`, `setInterval`, `setTimeout`, `Date.now()`, or CSS `@keyframes`.
   - Every movement, camera pan, mouth movement, and shot cut MUST be a pure mathematical function of `t_ms` (0 to {duration_ms}).

5. VISUAL POLISH & TYPOGRAPHY:
   - Rich color palettes with `<linearGradient>`, `<radialGradient>`, drop shadows, and bold `3px-4px` dark outlines (`#1a1a2e`) on characters.
   - NO subtitles. Use bold cinematic on-screen titles/labels (max 4 words: dates, locations, troop numbers) only when relevant cues hit.

6. AUTO SOUND EFFECTS (CRITICAL):
   - Inside the `<head>` of your HTML, you MUST include a JSON block defining the exact sound effects needed for the visual actions you created.
   - Format exactly like this: `<script id="sfx-data" type="application/json">[{"time_ms": 1500, "prompt": "sharp sword clash"}, {"time_ms": 4200, "prompt": "cannon fire"}]</script>`
   - The `time_ms` MUST perfectly match the visual actions driven by your `window.updateSceneTime` function.

7. OUTPUT:
   - Output ONLY the standalone HTML code wrapped inside a single ```html ... ``` block. No explanations.
'''.strip()


def build_timeline(chunk_segments, chunk_start, chunk_duration):
  lines = []
  current_pos = 0.0

  for sg in chunk_segments:
    a = max(round(sg.start - chunk_start, 1), 0.0)
    b = min(max(round(sg.end - chunk_start, 1), 0.0), round(chunk_duration, 1))

    if a > current_pos + 0.3:
      lines.append(
          f"[{current_pos:.1f}s - {a:.1f}s] Visual Setup: Cinematic establishing shot & camera pan"
      )
    lines.append(f"[{a:.1f}s - {b:.1f}s] Narration & Action: {sg.text.strip()}")
    current_pos = max(current_pos, b)

  if current_pos < chunk_duration - 0.3:
    lines.append(
        f"[{current_pos:.1f}s - {chunk_duration:.1f}s] Visual Hold: Dramatic reaction & transition zoom"
    )

  return "\\n".join(lines)


def generate_ai_bgm(prompt_text, output_filename="background_music.mp3"):
    print(f"Generating Auto AI BGM for: {prompt_text}", flush=True)
    API_URL = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
    hf_token = os.environ.get("HF_TOKEN", "")
    
    if not hf_token:
        print("Warning: HF_TOKEN not found. Skipping BGM generation.", flush=True)
        return False
        
    headers = {"Authorization": f"Bearer {hf_token}"}
    
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt_text})
        if response.status_code == 200:
            with open(output_filename, "wb") as f:
                f.write(response.content)
            print("Background music successfully generated!", flush=True)
            return True
        else:
            print(f"Failed to generate music: {response.text}", flush=True)
            return False
    except Exception as e:
        print(f"Error generating BGM: {e}", flush=True)
        return False


def main():
  from faster_whisper import WhisperModel
  from pydub import AudioSegment

  os.makedirs(OUT, exist_ok=True)
  print(f"Loading {AUDIO_FILE} ...", flush=True)
  audio = AudioSegment.from_file(AUDIO_FILE)
  
  # --- AUTO BGM GENERATION & MIXING ---
  bgm_file = "background_music.mp3"
  music_prompt = "Epic historical documentary background music, cinematic orchestra, fast-paced, suspenseful, no vocals"
  
  if generate_ai_bgm(music_prompt, bgm_file):
      try:
          print("Mixing Background Music with voiceover...", flush=True)
          bgm = AudioSegment.from_file(bgm_file)
          bgm = bgm - 16  # ভলিউম 16 dB কমানো
          
          # ভয়েসওভারের সমান করার জন্য লুপ করা
          loops_needed = int(len(audio) / len(bgm)) + 1
          bgm_looped = bgm * loops_needed
          bgm_looped = bgm_looped[:len(audio)]
          
          # মূল অডিওর সাথে মিক্স করা
          audio = audio.overlay(bgm_looped)
          print("BGM Mixed successfully!", flush=True)
      except Exception as e:
          print(f"Error mixing BGM: {e}", flush=True)
  # ------------------------------------

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
        or f"[0.0s - {duration:.1f}s] Action: {text}"
    )
    prompt = build_cartoon_rigging_prompt(text, duration, timeline, chunk_idx=i)

    with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
      f.write(prompt)
    combined.append(f"===== PROMPT {i} =====\\n{prompt}\\n")

    meta.append({
        "index": i,
        "duration": duration,
        "text": text,
        "timeline": timeline,
    })
    print(f"Chunk {i}: {duration:.1f}s | {text[:60]}...", flush=True)

  with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
    f.write("\\n\\n".join(combined))
  with open(f"{OUT}/chunks.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

  print(f"Done: {OUT}/ ({len(chunks)} chunks created)", flush=True)

if __name__ == "__main__":
  main()
""")
print("Fixed file created.")
