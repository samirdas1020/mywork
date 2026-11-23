import glob
import hashlib
import json
import os
import subprocess
import sys
import numpy as np
from scipy.io.wavfile import write as write_wav

FPS = 30
WIDTH, HEIGHT = 720, 1280
SCALE = 1.5
IN_DIR = "render_input"
OUT_DIR = "clips"

STEP_JS = """t => {
  document.getAnimations().forEach(a => {
    try { a.pause(); a.currentTime = t; } catch (e) {}
  });
  document.querySelectorAll('svg').forEach(s => {
    try { s.pauseAnimations(); s.setCurrentTime(t / 1000); } catch (e) {}
  });
  if (window.updateSceneTime) window.updateSceneTime(t);
}"""

INIT_JS = """
window.requestAnimationFrame = () => 0;
window.setInterval = () => 0;
window.setTimeout = () => 0;
"""


def synthesize_sfx_from_params(sfx_item, output_wav="temp_sfx.wav", sr=22050):
  """JSON প্যারামিটার অনুযায়ী লোকালি (API ছাড়া) স্টাইলাইজড SFX তৈরি করে।"""
  sfx_type = str(sfx_item.get("type", "")).lower().strip()
  prompt_text = str(sfx_item.get("prompt", "")).lower()
  duration_sec = float(np.clip(sfx_item.get("duration_ms", 650), 120, 2000)) / 1000.0
  intensity = float(np.clip(sfx_item.get("intensity", 0.75), 0.15, 1.0))

  if not sfx_type:
    if any(k in prompt_text for k in ["cannon", "boom", "impact", "explosion", "fire"]):
      sfx_type = "impact"
    elif any(k in prompt_text for k in ["sword", "clash", "metal", "blade"]):
      sfx_type = "metal"
    elif any(k in prompt_text for k in ["swoosh", "whoosh", "wind", "arrow"]):
      sfx_type = "swoosh"
    elif any(k in prompt_text for k in ["drum", "march", "step", "foot"]):
      sfx_type = "drum"
    elif any(k in prompt_text for k in ["horn", "alarm", "brass", "war"]):
      sfx_type = "horn"
    else:
      sfx_type = "cue"

  t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
  if len(t) == 0:
    t = np.linspace(0, 0.3, int(sr * 0.3), endpoint=False)

  if sfx_type == "impact":
    f0 = float(np.clip(sfx_item.get("base_freq", 65), 35, 140))
    noise = np.random.normal(0, 1, len(t))
    env = np.exp(-5.2 * t / max(duration_sec, 0.2))
    sub = np.sin(2 * np.pi * (f0 * np.exp(-2.8 * t) + 28) * t)
    wave = (0.65 * sub + 0.45 * noise) * env

  elif sfx_type == "metal":
    f0 = float(np.clip(sfx_item.get("base_freq", 750), 300, 1800))
    env = np.sin(np.pi * np.clip(t / duration_sec, 0, 1)) ** 1.6
    vib = 1.0 + 0.015 * np.sin(2 * np.pi * 28 * t)
    wave = (
        0.50 * np.sin(2 * np.pi * f0 * vib * t)
        + 0.32 * np.sin(2 * np.pi * (f0 * 2.41) * t)
        + 0.18 * np.sin(2 * np.pi * (f0 * 3.17) * t + 0.5)
    ) * env

  elif sfx_type == "swoosh":
    f0 = float(np.clip(sfx_item.get("base_freq", 240), 120, 700))
    sweep = f0 + (f0 * 3.2) * np.sin(np.pi * np.clip(t / duration_sec, 0, 1))
    env = np.sin(np.pi * np.clip(t / duration_sec, 0, 1)) ** 1.3
    band = np.sin(2 * np.pi * sweep * t) * 0.6 + np.random.normal(0, 0.4, len(t))
    wave = band * env

  elif sfx_type == "drum":
    f0 = float(np.clip(sfx_item.get("base_freq", 95), 55, 180))
    hit_env = np.exp(-9.0 * (t % max(0.28, duration_sec / 2.0)))
    pitch_curve = f0 * (1.0 + 0.6 * np.exp(-18.0 * t))
    wave = np.sin(2 * np.pi * pitch_curve * t) * hit_env

  elif sfx_type == "horn":
    f0 = float(np.clip(sfx_item.get("base_freq", 146.83), 90, 350))
    attack = np.clip(t / 0.08, 0, 1)
    release = np.clip((duration_sec - t) / 0.15, 0, 1)
    env = attack * release
    wave = (
        0.55 * np.sin(2 * np.pi * f0 * t)
        + 0.30 * np.sin(2 * np.pi * (f0 * 2) * t)
        + 0.15 * np.sin(2 * np.pi * (f0 * 3) * t)
    ) * env

  else:  # "cue"
    f0 = float(np.clip(sfx_item.get("base_freq", 260), 150, 600))
    env = np.exp(-4.5 * t / max(duration_sec, 0.2))
    wave = (
        0.65 * np.sin(2 * np.pi * f0 * t)
        + 0.25 * np.sin(2 * np.pi * f0 * 1.5 * t)
    ) * env

  kernel = np.ones(9) / 9.0
  wave = np.convolve(wave, kernel, mode="same")
  peak = np.max(np.abs(wave)) or 1.0
  scaled = np.clip((wave / peak) * 0.55 * intensity, -1.0, 1.0)
  audio_int16 = np.int16(scaled * 32767)
  write_wav(output_wav, sr, audio_int16)
  return output_wav


def render(i):
  from playwright.sync_api import sync_playwright
  from pydub import AudioSegment

  with open(f"{IN_DIR}/chunks.json", encoding="utf-8") as f:
    meta = {c["index"]: c for c in json.load(f)}

  duration = float(meta[i]["duration"])
  frames = max(1, round(duration * FPS))

  hyphen_scene = os.path.abspath(f"{IN_DIR}/scene-{i}.html")
  scene = os.path.abspath(f"{IN_DIR}/scene_{i}.html")
  if os.path.exists(hyphen_scene) and not os.path.exists(scene):
    os.rename(hyphen_scene, scene)

  audio = f"{IN_DIR}/audio_{i}.mp3"
  os.makedirs(OUT_DIR, exist_ok=True)
  video = f"{OUT_DIR}/video_{i}.mp4"
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

    # --- LOCAL PARAMETERIZED SFX SYNTHESIS & MIXING ---
    try:
      sfx_json = page.evaluate(
          "() => document.getElementById('sfx-data') ?"
          " document.getElementById('sfx-data').textContent : '[]'"
      )
      sfx_list = json.loads(sfx_json)

      if isinstance(sfx_list, list) and sfx_list and os.path.exists(audio):
        main_audio = AudioSegment.from_file(audio)
        max_audio_ms = len(main_audio)

        for idx, sfx in enumerate(sfx_list):
          if not isinstance(sfx, dict):
            continue
          time_ms = int(
              np.clip(sfx.get("time_ms", 0), 0, max(0, max_audio_ms - 50))
          )
          wav_path = os.path.join(OUT_DIR, f"sfx_{i}_{idx}.wav")
          try:
            synthesize_sfx_from_params(sfx, wav_path)
            new_sfx = AudioSegment.from_wav(wav_path) - 3
            main_audio = main_audio.overlay(new_sfx, position=time_ms)
            print(
                f"Synthesized & mixed [{sfx.get('type', 'auto')}] at {time_ms}ms",
                flush=True,
            )
          finally:
            if os.path.exists(wav_path):
              os.remove(wav_path)

        main_audio.export(audio, format="mp3")
        print("Local SFX mixing complete!", flush=True)
    except Exception as e:
      print(f"Local SFX skipped/failed globally: {e}", flush=True)
    # -------------------------------------------------

    for f in range(frames):
      t = f * 1000.0 / FPS
      page.evaluate(STEP_JS, t)
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

  if os.path.exists(audio):
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
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            "apad",
            "-shortest",
            final,
        ],
        check=True,
    )
    os.remove(video)
  else:
    os.replace(video, final)
  print(f"Saved {final}", flush=True)


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
    raise SystemExit("usage: render_vector_shorts.py render N | merge")
