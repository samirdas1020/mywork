import array
import glob
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import wave

FPS = 30
WIDTH, HEIGHT = 720, 1280
SCALE = 1.5  # Renders 720x1280 canvas directly as 1080x1920 (Full HD Vertical)
IN_DIR = "render_input"  # scene_N.html, audio_N.mp3, chunks.json
OUT_DIR = "clips"

# Inspects discrete active shots and visible titles at frame time t
STEP_JS = """t => {
  document.getAnimations().forEach(a => {
    try { a.pause(); a.currentTime = t; } catch (e) {}
  });
  document.querySelectorAll('svg').forEach(s => {
    try { s.pauseAnimations(); s.setCurrentTime(t / 1000); } catch (e) {}
  });
  if (window.updateSceneTime) window.updateSceneTime(t);

  const isVisible = (el) => {
    let cur = el;
    while (cur && cur !== document.body) {
      const st = window.getComputedStyle(cur);
      if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') <= 0.15) {
        return false;
      }
      cur = cur.parentElement;
    }
    return true;
  };

  let activeShots = [];
  let visibleTexts = [];

  // 1. Detect Active Shot Group (id="shot-N", id="scene-N", or top-level <g>)
  const explicitShots = document.querySelectorAll('[id^="shot"], [id*="scene"]');
  if (explicitShots.length > 0) {
    explicitShots.forEach(el => {
      if (isVisible(el)) activeShots.push(el.id);
    });
  } else {
    document.querySelectorAll('svg > g').forEach((el, idx) => {
      if (isVisible(el)) activeShots.push(el.id || ('top_g_' + idx));
    });
  }

  // 2. Detect Visible On-Screen Titles / Dates / Labels
  document.querySelectorAll('text, [id*="title"], [id*="label"], [class*="title"]').forEach(el => {
    const txt = (el.textContent || '').trim();
    if (txt.length > 0 && isVisible(el)) {
      visibleTexts.push(txt.slice(0, 24));
    }
  });

  return {
    shots: activeShots.join('|'),
    texts: visibleTexts
  };
}"""

INIT_JS = """
window.requestAnimationFrame = () => 0;
window.setInterval = () => 0;
window.setTimeout = () => 0;
"""


def extract_timeline_cues(chunk_meta):
  """Extracts at most ONE clean contextual SFX per narration sentence."""
  cues = []
  timeline = chunk_meta.get("timeline", "")

  battle_kw = (
      r"\b(war|wars|battle|battles|sword|swords|attack|attacked|army|armies|"
      r"fight|fought|strike|struck|blood|kill|killed|soldier|soldiers|"
      r"warrior|warriors|combat|clash|spear|shield|blade|ambush|cannon|siege)\b"
  )
  impact_kw = (
      r"\b(empire|empires|fall|fell|fallen|death|dead|power|shock|betray|"
      r"betrayed|betrayal|defeat|defeated|collapse|collapsed|murder|doom|"
      r"disaster|crush|crushed|execute|executed|destroy|destroyed|invasion)\b"
  )
  shimmer_kw = (
      r"\b(gold|golden|treasure|rich|riches|crown|crowned|king|kings|queen|"
      r"throne|wealth|miracle|victory|victorious|glory|royal|fortune)\b"
  )

  for line in timeline.splitlines():
    m = re.match(r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(.*)", line)
    if not m:
      continue
    start_s = float(m.group(1))
    content = m.group(3)
    start_ms = int(start_s * 1000)

    if "Narration & Action:" in content:
      if re.search(battle_kw, content, re.IGNORECASE):
        cues.append(
            {"time_ms": start_ms + 300, "type": "sword", "intensity": 0.72}
        )
      elif re.search(impact_kw, content, re.IGNORECASE):
        cues.append(
            {"time_ms": start_ms + 250, "type": "boom", "intensity": 0.72}
        )
      elif re.search(shimmer_kw, content, re.IGNORECASE):
        cues.append(
            {"time_ms": start_ms + 300, "type": "shimmer", "intensity": 0.68}
        )

  return cues


def select_video_bgm_profile(all_meta):
  """Analyzes the full video script in chunks.json to pick a mood-matched

  chord progression, key transposition, tempo, and tone unique to EACH video,
  while keeping all chunks of the SAME video musically unified.
  """
  full_text = " ".join(
      c.get("text", "") for c in sorted(all_meta.values(), key=lambda x: x["index"])
  ).lower()
  video_hash = int(
      hashlib.md5((full_text or "default").encode("utf-8")).hexdigest()[:8], 16
  )

  # Count story mood keywords across the entire script
  war_score = len(
      re.findall(
          r"\b(war|battle|army|sword|attack|siege|invasion|soldier|fight|cannon|blood)\b",
          full_text,
      )
  )
  mystery_score = len(
      re.findall(
          r"\b(secret|mystery|betray|betrayal|plot|shadow|spy|poison|hidden|night|conspiracy)\b",
          full_text,
      )
  )
  royal_score = len(
      re.findall(
          r"\b(king|queen|emperor|crown|throne|gold|wealth|empire|dynasty|royal|palace|victory)\b",
          full_text,
      )
  )
  tragic_score = len(
      re.findall(
          r"\b(fall|collapse|death|dead|plague|famine|ruin|destroy|disaster|doom|end|tragedy)\b",
          full_text,
      )
  )

  # Base progressions: Each chord is (Bass, Pad1, Pad2, Pad3, Note1, Note2) in Hz
  progressions = {
      "war": [
          # Intense Phrygian / Dark Tactical War Progression (Em -> C -> Am -> B)
          (164.81, 246.94, 329.63, 392.00, 659.25, 587.33),
          (130.81, 261.63, 329.63, 392.00, 523.25, 659.25),
          (110.00, 220.00, 261.63, 329.63, 523.25, 440.00),
          (123.47, 246.94, 293.66, 369.99, 493.88, 587.33),
      ],
      "mystery": [
          # Dark Suspense Dorian / Conspiracy Progression (Cm -> Ab -> Fm -> G)
          (130.81, 196.00, 261.63, 311.13, 523.25, 622.25),
          (103.83, 207.65, 261.63, 311.13, 523.25, 415.30),
          (174.61, 261.63, 349.23, 415.30, 523.25, 698.46),
          (196.00, 246.94, 293.66, 392.00, 587.33, 493.88),
      ],
      "royal": [
          # Majestic Imperial Progression (Am -> F -> C -> G)
          (110.00, 220.00, 261.63, 329.63, 523.25, 659.25),
          (174.61, 261.63, 349.23, 440.00, 698.46, 523.25),
          (130.81, 261.63, 329.63, 392.00, 659.25, 523.25),
          (196.00, 246.94, 293.66, 392.00, 587.33, 493.88),
      ],
      "tragic": [
          # Emotional Melancholic Minor Progression (Dm -> Bb -> Gm -> A)
          (146.83, 220.00, 293.66, 349.23, 587.33, 440.00),
          (116.54, 233.08, 293.66, 349.23, 587.33, 523.25),
          (196.00, 233.08, 293.66, 392.00, 587.33, 466.16),
          (110.00, 220.00, 277.18, 329.63, 554.37, 440.00),
      ],
  }

  scores = {
      "war": war_score,
      "mystery": mystery_score,
      "royal": royal_score,
      "tragic": tragic_score,
  }
  best_mood = max(scores, key=scores.get)
  if scores[best_mood] == 0:
    best_mood = ["war", "mystery", "royal", "tragic"][video_hash % 4]

  # Transpose musical key by -2 to +3 semitones based on video_hash so every video is unique!
  semitone_shift = [-2, -1, 0, 1, 2, 3][video_hash % 6]
  pitch_ratio = 2.0 ** (semitone_shift / 12.0)

  # Vary chord duration (tempo) between 2.6s and 3.4s per video
  chord_dur = [2.6, 2.8, 3.0, 3.3][(video_hash // 7) % 4]

  # Apply pitch transposition to the chosen chord progression
  raw_chords = progressions[best_mood]
  transposed_chords = [
      tuple(f * pitch_ratio for f in ch) for ch in raw_chords
  ]

  return {
      "mood": best_mood,
      "semitones": semitone_shift,
      "chord_dur": chord_dur,
      "chords": transposed_chords,
      "video_hash": video_hash,
  }


def synth_chord_pad(t, chord_freqs, mood="royal"):
  """Synthesizes a warm, pitch-stable orchestral pad tailored to the story mood."""
  bass_f, p1_f, p2_f, p3_f, _, _ = chord_freqs
  two_pi = 2.0 * math.pi

  # War & Tragic moods get deeper brass/cello warmth; Mystery & Royal get airy strings
  brass_boost = 0.24 if mood in ("war", "tragic") else 0.16

  return (
      0.26 * math.sin(two_pi * bass_f * t)
      + brass_boost * math.sin(two_pi * (bass_f * 2.0) * t)
      + 0.18 * math.sin(two_pi * (p1_f * 0.998) * t)
      + 0.18 * math.sin(two_pi * (p1_f * 1.002) * t)
      + 0.16 * math.sin(two_pi * (p2_f * 0.9985) * t)
      + 0.16 * math.sin(two_pi * (p2_f * 1.0015) * t)
      + 0.14 * math.sin(two_pi * p3_f * t)
  )


def generate_bgm_wav(duration, out_wav, profile, chunk_idx=0):
  """Generates a unique, story-matched Cinematic BGM track for the video."""
  sr = 44100
  total_samples = max(1, int(duration * sr))
  buf = [0.0] * total_samples

  chord_dur = profile["chord_dur"]
  half_dur = chord_dur * 0.5
  xfade_dur = min(0.75, chord_dur * 0.28)
  chords = profile["chords"]
  mood = profile["mood"]

  two_pi = 2.0 * math.pi

  for idx in range(total_samples):
    t = idx / sr
    c_num = int(t / chord_dur)
    c_idx = (c_num + chunk_idx) % 4
    next_idx = (c_num + 1 + chunk_idx) % 4
    c_t = t % chord_dur

    # Seamless constant-power crossfade between chords
    pad_cur = synth_chord_pad(t, chords[c_idx], mood=mood)
    if c_t > (chord_dur - xfade_dur):
      alpha = (c_t - (chord_dur - xfade_dur)) / xfade_dur
      w_cur = math.cos(0.5 * math.pi * alpha)
      w_nxt = math.sin(0.5 * math.pi * alpha)
      pad_nxt = synth_chord_pad(t, chords[next_idx], mood=mood)
      strings = w_cur * pad_cur + w_nxt * pad_nxt
    else:
      strings = pad_cur

    # Slow, graceful 2-note melodic motif per chord (spaced ~1.4s - 1.6s apart)
    note_f = chords[c_idx][4] if c_t < half_dur else chords[c_idx][5]
    note_t = c_t if c_t < half_dur else (c_t - half_dur)
    bell_attack = 1.0 - math.exp(-75.0 * note_t)
    bell_decay = math.exp(-2.6 * note_t)
    melody_note = (
        0.22
        * bell_attack
        * bell_decay
        * (
            0.70 * math.sin(two_pi * note_f * note_t)
            + 0.22 * math.sin(two_pi * (note_f * 2.0) * note_t)
            + 0.08 * math.sin(two_pi * (note_f * 3.0) * note_t)
        )
    )

    buf[idx] = 0.50 * (strings + melody_note)

  # Smooth fade-in and fade-out at clip boundaries
  fade_samples = min(int(0.06 * sr), total_samples // 4)
  pcm = array.array("h")
  for idx, x in enumerate(buf):
    gain = 1.0
    if idx < fade_samples and fade_samples > 0:
      gain = idx / fade_samples
    elif idx >= total_samples - fade_samples and fade_samples > 0:
      gain = (total_samples - 1 - idx) / fade_samples
    limited = math.tanh(x * gain) * 0.90
    pcm.append(int(max(-32767, min(32767, limited * 32767))))

  with wave.open(out_wav, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm.tobytes())


def generate_sfx_wav(duration, cues, out_wav, seed=0):
  """Generates clean, single-hit Sound Effects with a strict 2.5s Global Cooldown.

  Guarantees two sounds NEVER play together or back-to-back!
  """
  sr = 44100
  total_samples = max(1, int(duration * sr))
  buf = [0.0] * total_samples
  rng = random.Random(2026 + seed)

  def add_sample(idx, val):
    if 0 <= idx < total_samples:
      buf[idx] += val

  # STRICT GLOBAL COOLDOWN: Minimum 2500ms (2.5 seconds) between ANY two sound effects!
  priority = {"whoosh": 1, "boom": 2, "sword": 3, "shimmer": 4, "pop": 5}
  cues = sorted(
      cues,
      key=lambda x: (x.get("time_ms", 0), priority.get(x.get("type", "pop"), 9)),
  )

  filtered_cues = []
  last_cue_ms = -9999.0
  MIN_GLOBAL_GAP_MS = 2500.0

  for c in cues:
    tms = float(c.get("time_ms", 0))
    if tms - last_cue_ms >= MIN_GLOBAL_GAP_MS:
      filtered_cues.append(c)
      last_cue_ms = tms

  for cue in filtered_cues:
    t0 = float(cue.get("time_ms", 0)) / 1000.0
    ctype = str(cue.get("type", "whoosh")).lower()
    intensity = min(max(float(cue.get("intensity", 0.75)), 0.2), 1.0)
    start_idx = int(t0 * sr)

    if ctype == "boom":
      dur = 0.80
      n = int(dur * sr)
      phase = 0.0
      lp = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-5.2 * u)
        freq = 42.0 + 80.0 * math.exp(-16.0 * u)
        phase += 2.0 * math.pi * freq / sr
        noise = rng.random() * 2.0 - 1.0
        lp = 0.90 * lp + 0.10 * noise
        val = (
            0.75 * math.tanh(1.5 * math.sin(phase))
            + 0.25 * lp * math.exp(-15.0 * u)
        ) * env
        add_sample(start_idx + k, val * 0.68 * intensity)

    elif ctype == "whoosh":
      dur = 0.32
      n = int(dur * sr)
      lp = 0.0
      phase = 0.0
      for k in range(n):
        u = k / n
        env = math.sin(math.pi * u) ** 1.8
        alpha = 0.05 + 0.30 * math.sin(math.pi * u)
        noise = rng.random() * 2.0 - 1.0
        lp = (1.0 - alpha) * lp + alpha * noise
        freq = 150.0 + 210.0 * math.sin(math.pi * u)
        phase += 2.0 * math.pi * freq / sr
        val = (0.70 * lp + 0.30 * math.sin(phase)) * env
        add_sample(start_idx + k, val * 0.58 * intensity)

    elif ctype == "sword":
      dur = 0.38
      n = int(dur * sr)
      freqs = [1220.0, 1810.0, 2540.0, 3420.0]
      for k in range(n):
        u = k / sr
        env = math.exp(-12.5 * u)
        ring = sum(math.sin(2.0 * math.pi * f * u) for f in freqs) / len(freqs)
        burst = (rng.random() * 2.0 - 1.0) * math.exp(-48.0 * u)
        val = (0.72 * ring + 0.28 * burst) * env
        add_sample(start_idx + k, val * 0.52 * intensity)

    elif ctype == "shimmer":
      dur = 0.60
      n = int(dur * sr)
      freqs = [1046.50, 1318.51, 1567.98, 2093.00]
      for k in range(n):
        u = k / sr
        env = math.exp(-7.5 * u)
        bell = sum(
            math.sin(2.0 * math.pi * f * u) * math.exp(-i * 1.2 * u)
            for i, f in enumerate(freqs)
        ) / len(freqs)
        add_sample(start_idx + k, bell * env * 0.48 * intensity)

    elif ctype == "pop":
      dur = 0.085
      n = int(dur * sr)
      phase = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-40.0 * u)
        freq = 340.0 + 400.0 * math.exp(-48.0 * u)
        phase += 2.0 * math.pi * freq / sr
        val = math.sin(phase) * env
        add_sample(start_idx + k, val * 0.48 * intensity)

  pcm = array.array("h")
  for x in buf:
    limited = math.tanh(x) * 0.90
    pcm.append(int(max(-32767, min(32767, limited * 32767))))

  with wave.open(out_wav, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm.tobytes())

  return len(filtered_cues)


def render(i):
  from playwright.sync_api import sync_playwright

  with open(f"{IN_DIR}/chunks.json", encoding="utf-8") as f:
    meta = {c["index"]: c for c in json.load(f)}

  chunk_meta = meta[i]
  duration = float(chunk_meta["duration"])
  frames = max(1, round(duration * FPS))

  hyphen_scene = os.path.abspath(f"{IN_DIR}/scene-{i}.html")
  scene = os.path.abspath(f"{IN_DIR}/scene_{i}.html")
  if os.path.exists(hyphen_scene) and not os.path.exists(scene):
    os.rename(hyphen_scene, scene)

  audio = f"{IN_DIR}/audio_{i}.mp3"
  os.makedirs(OUT_DIR, exist_ok=True)
  video = f"{OUT_DIR}/video_{i}.mp4"
  bgm_wav = f"{OUT_DIR}/bgm_{i}.wav"
  sfx_wav = f"{OUT_DIR}/sfx_{i}.wav"
  final = f"{OUT_DIR}/synced_{i}.mp4"

  print(
      f"Shorts Chunk {i}: {duration}s, {frames} frames"
      f" ({int(WIDTH*SCALE)}x{int(HEIGHT*SCALE)})",
      flush=True,
  )

  ff = subprocess.Popen(
      [
          "ffmpeg",
          "-y",
          "-loglevel",
          "error",
          "-f",
          "image2pipe",
          "-framerate",
          str(FPS),
          "-c:v",
          "mjpeg",
          "-i",
          "-",
          "-c:v",
          "libx264",
          "-preset",
          "veryfast",
          "-crf",
          "18",
          "-pix_fmt",
          "yuv420p",
          video,
      ],
      stdin=subprocess.PIPE,
  )

  seen = set()
  errors = []

  # Single opening impact at 0ms
  auto_cues = [{"time_ms": 0, "type": "boom", "intensity": 0.78}]
  auto_cues.extend(extract_timeline_cues(chunk_meta))

  seen_shots = set()
  seen_texts = set()

  with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
        viewport={"width": WIDTH, "height": HEIGHT},
        device_scale_factor=SCALE,
    )
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(INIT_JS)
    page.goto("file://" + scene, wait_until="load")
    page.wait_for_timeout(500)

    for f in range(frames):
      t = f * 1000.0 / FPS
      state = page.evaluate(STEP_JS, t)

      if isinstance(state, dict):
        cur_shots = state.get("shots", "")
        cur_texts = state.get("texts", [])

        # Record initial shot & text state at frame 0 without triggering extra SFX
        if f == 0:
          if cur_shots:
            seen_shots.add(cur_shots)
          for txt in cur_texts:
            seen_texts.add(txt)
        else:
          # 1. Trigger Whoosh ONLY when switching to a brand-new shot never seen before
          if cur_shots and cur_shots not in seen_shots:
            seen_shots.add(cur_shots)
            auto_cues.append(
                {"time_ms": round(t), "type": "whoosh", "intensity": 0.78}
            )

          # 2. Trigger Pop ONLY when a brand-new text label appears for the first time
          for txt in cur_texts:
            if txt not in seen_texts:
              seen_texts.add(txt)
              auto_cues.append(
                  {"time_ms": round(t), "type": "pop", "intensity": 0.68}
              )
              break

      img = page.screenshot(type="jpeg", quality=95)
      ff.stdin.write(img)
      if f % 5 == 0:
        seen.add(hashlib.md5(img).hexdigest())
      if f % 120 == 0:
        print(f"  frame {f}/{frames}", flush=True)
    browser.close()

  ff.stdin.close()
  if ff.wait() != 0:
    raise SystemExit("ffmpeg video encode failed")

  if errors:
    print("Page JS errors:", errors[:3], flush=True)
  if len(seen) <= 1:
    print("WARNING: frames look static, check the HTML.", flush=True)

  # Select Story-Matched BGM Profile unique to this video + Generate BGM & SFX
  bgm_profile = select_video_bgm_profile(meta)
  generate_bgm_wav(duration, bgm_wav, bgm_profile, chunk_idx=i)
  kept_sfx = generate_sfx_wav(duration, auto_cues, sfx_wav, seed=i)
  print(
      f"  BGM Mood: '{bgm_profile['mood'].upper()}' (Key shift:"
      f" {bgm_profile['semitones']:+d} st, Tempo: {bgm_profile['chord_dur']}s)"
      f" + {kept_sfx} Unique SFX...",
      flush=True,
  )

  if os.path.exists(audio):
    # Mix 3 tracks cleanly: Voice = 100%, BGM = 38% steady, SFX = 48%
    filter_graph = (
        f"[1:a]volume=1.0,apad=whole_dur={duration}[vo];"
        f"[2:a]volume=0.38[bgm];"
        f"[3:a]volume=0.48[sfx];"
        f"[vo][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=0,"
        f"volume=2.85,alimiter=limit=0.95[aout]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video,
            "-i",
            audio,
            "-i",
            bgm_wav,
            "-i",
            sfx_wav,
            "-filter_complex",
            filter_graph,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            final,
        ],
        check=True,
    )
    os.remove(video)
  else:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video,
            "-i",
            bgm_wav,
            "-i",
            sfx_wav,
            "-filter_complex",
            "[1:a]volume=0.65[bgm];[2:a]volume=0.75[sfx];[bgm][sfx]amix=inputs=2:duration=first,volume=1.9,alimiter=limit=0.95[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            final,
        ],
        check=True,
    )
    os.remove(video)

  for tmp_f in (bgm_wav, sfx_wav):
    if os.path.exists(tmp_f):
      os.remove(tmp_f)
  print(
      f"Saved {final} (Story-Matched '{bgm_profile['mood']}' BGM & Clean SFX)",
      flush=True,
  )


def merge():
  files = glob.glob(f"{OUT_DIR}/synced_*.mp4")
  files.sort(key=lambda p: int(os.path.basename(p).split("_")[1].split(".")[0]))
  if not files:
    raise SystemExit("No clips found to merge")

  with open("concat.txt", "w", encoding="utf-8") as f:
    for p in files:
      f.write(f"file '{os.path.abspath(p)}'\n")

  subprocess.run(
      [
          "ffmpeg",
          "-y",
          "-loglevel",
          "error",
          "-f",
          "concat",
          "-safe",
          "0",
          "-i",
          "concat.txt",
          "-c:v",
            "copy",
          "-c:a",
          "aac",
          "-b:a",
          "192k",
          "-movflags",
          "+faststart",
          "final_shorts.mp4",
      ],
      check=True,
  )
  print(f"Merged {len(files)} clips -> final_shorts.mp4 (1080x1920)", flush=True)


if __name__ == "__main__":
  mode = sys.argv[1]
  if mode == "render":
    render(int(sys.argv[2]))
  elif mode == "merge":
    merge()
  else:
    raise SystemExit("usage: render_shorts_scenes.py render N | merge")
