import json
import os
import numpy as np
from scipy.io.wavfile import write as write_wav

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TARGET_CHUNK_SEC = 30.0
WIDTH, HEIGHT = 720, 1280


def build_cartoon_rigging_prompt(scene_text, duration, timeline="", chunk_idx=0):
  duration_ms = int(duration * 1000)
  min_shots = max(4, int(round(duration / 5.0)))

  return f"""
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
   - Let the visual actions you create in `window.updateSceneTime` decide which sounds happen and when (`time_ms`).
   - Put `<script id="sfx-data" type="application/json">[...]</script>` inside `<head>` with items containing `time_ms`, `type`, `base_freq`, `duration_ms`, `intensity`, and `prompt`.
   - Vary values dynamically per action so repeated cues do not sound identical.

7. OUTPUT:
   - Output ONLY the standalone HTML code wrapped inside a single ```html ... ``` block. No explanations.
""".strip()


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

  return "\n".join(lines)


def create_dynamic_bgm(
    output_wav="dynamic_bgm.wav",
    duration_sec=12.0,
    scene_text="",
    chunk_idx=0,
    sr=22050,
):
  """ন্যারেশনের মুড ও চাঙ্ক অনুযায়ী ডাইনামিক সিন্থেসাইজড BGM তৈরি করে।"""
  duration_sec = max(float(duration_sec), 2.0)
  t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
  text = (scene_text or "").lower()

  # মুড নির্ধারণ: battle/action vs triumph/rise vs suspense/strategy
  if any(
      k in text
      for k in [
          "war",
          "battle",
          "attack",
          "army",
          "fight",
          "invade",
          "cannon",
          "siege",
          "collapse",
          "fall",
      ]
  ):
    mood = "battle"
    scale_ratios = [1.0, 1.189, 1.335, 1.498, 1.782, 2.0]  # Phrygian / dark minor
    pulse_hz = 3.2 + (chunk_idx % 3) * 0.45
    root_base = 65.41 + (chunk_idx % 4) * 5.5
  elif any(
      k in text
      for k in [
          "victory",
          "win",
          "rise",
          "empire",
          "golden",
          "peace",
          "freedom",
          "triumph",
          "treaty",
      ]
  ):
    mood = "triumph"
    scale_ratios = [1.0, 1.25, 1.498, 1.875, 2.0, 2.5]  # Major / heroic fifths
    pulse_hz = 2.2 + (chunk_idx % 2) * 0.35
    root_base = 82.41 + (chunk_idx % 4) * 6.0
  else:
    mood = "suspense"
    scale_ratios = [1.0, 1.122, 1.335, 1.498, 1.587, 2.0]  # Dorian / tense mystery
    pulse_hz = 1.7 + (chunk_idx % 3) * 0.3
    root_base = 73.42 + (chunk_idx % 4) * 4.5

  # চাঙ্ক ও টেক্সট হ্যাশ থেকে ডিটারমিনিস্টিক নোট সিকোয়েন্স তৈরি
  seed_val = (chunk_idx * 9973 + sum(ord(c) for c in text)) % (2**31 - 1)
  rng = np.random.default_rng(seed_val)

  bar_sec = 1.5 if mood == "battle" else 2.0
  num_bars = max(1, int(np.ceil(duration_sec / bar_sec)))
  note_indices = rng.integers(0, len(scale_ratios), size=num_bars)
  arp_indices = rng.integers(0, len(scale_ratios), size=num_bars * 2)

  # বেস ও অস্থায়ী মেলোডি লেয়ার
  bass_wave = np.zeros_like(t)
  arp_wave = np.zeros_like(t)
  pad_wave = np.zeros_like(t)

  for b in range(num_bars):
    start_t = b * bar_sec
    end_t = min((b + 1) * bar_sec, duration_sec)
    mask = (t >= start_t) & (t < end_t)
    if not np.any(mask):
      continue
    local_t = t[mask] - start_t
    env = np.sin(np.pi * np.clip(local_t / max(end_t - start_t, 0.05), 0, 1)) ** 0.65

    root_freq = root_base * scale_ratios[note_indices[b]]
    bass_wave[mask] += (
        0.55 * np.sin(2 * np.pi * root_freq * local_t)
        + 0.25 * np.sin(2 * np.pi * (root_freq * 0.5) * local_t)
    ) * env
    pad_wave[mask] += (
        0.22 * np.sin(2 * np.pi * root_freq * 2.0 * local_t)
        + 0.14 * np.sin(2 * np.pi * root_freq * 3.0 * local_t + 0.4)
    ) * (0.6 + 0.4 * env)

  half_bar = bar_sec / 2.0
  for step in range(num_bars * 2):
    s_t = step * half_bar
    e_t = min((step + 1) * half_bar, duration_sec)
    mask = (t >= s_t) & (t < e_t)
    if not np.any(mask):
      continue
    local_t = t[mask] - s_t
    pluck_env = np.exp(-5.5 * local_t)
    arp_freq = root_base * 2.0 * scale_ratios[arp_indices[step]]
    arp_wave[mask] += 0.24 * np.sin(2 * np.pi * arp_freq * local_t) * pluck_env

  # সময় অনুযায়ী ধীরে ধীরে গতি/তীব্রতা বদলানো
  swell = 0.72 + 0.28 * np.sin(2 * np.pi * (0.08 + (chunk_idx % 3) * 0.03) * t)
  pulse = 0.75 + 0.25 * np.sin(2 * np.pi * pulse_hz * t)

  wave = (bass_wave + arp_wave + pad_wave) * pulse * swell

  kernel_size = 11 if mood == "battle" else 21
  kernel = np.ones(kernel_size) / float(kernel_size)
  wave = np.convolve(wave, kernel, mode="same")

  peak = np.max(np.abs(wave)) or 1.0
  audio_int16 = np.int16(np.clip((wave / peak) * 0.48, -1.0, 1.0) * 32767)
  write_wav(output_wav, sr, audio_int16)
  return output_wav, mood


def main():
  from faster_whisper import WhisperModel
  from pydub import AudioSegment

  os.makedirs(OUT, exist_ok=True)
  print(f"Loading {AUDIO_FILE} ...", flush=True)
  voice_audio = AudioSegment.from_file(AUDIO_FILE)

  total = len(voice_audio) / 1000.0
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

    chunk_voice = voice_audio[int(start * 1000) : int(end * 1000)]

    # প্রতিটি চাঙ্কের জন্য ডাইনামিক BGM তৈরি ও ভয়েসের সাথে মিক্সিং
    wav_bgm = os.path.join(OUT, f"bgm_{i}.wav")
    try:
      _, mood = create_dynamic_bgm(
          output_wav=wav_bgm,
          duration_sec=duration,
          scene_text=text,
          chunk_idx=i,
      )
      bgm_seg = AudioSegment.from_wav(wav_bgm) - 16
      if len(bgm_seg) < len(chunk_voice):
        loops = int(len(chunk_voice) / len(bgm_seg)) + 1
        bgm_seg = (bgm_seg * loops)[: len(chunk_voice)]
      else:
        bgm_seg = bgm_seg[: len(chunk_voice)]
      mixed_chunk_audio = chunk_voice.overlay(bgm_seg)
    finally:
      if os.path.exists(wav_bgm):
        os.remove(wav_bgm)

    mixed_chunk_audio.export(f"{OUT}/audio_{i}.mp3", format="mp3")

    timeline = (
        build_timeline(chunk_segs, start, duration)
        or f"[0.0s - {duration:.1f}s] Action: {text}"
    )
    prompt = build_cartoon_rigging_prompt(text, duration, timeline, chunk_idx=i)

    with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
      f.write(prompt)
    combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

    meta.append({
        "index": i,
        "duration": duration,
        "text": text,
        "mood": mood,
        "timeline": timeline,
    })
    print(f"Chunk {i} [{mood}]: {duration:.1f}s | {text[:60]}...", flush=True)

  with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(combined))
  with open(f"{OUT}/chunks.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

  print(f"Done: {OUT}/ ({len(chunks)} chunks created)", flush=True)


if __name__ == "__main__":
  main()
