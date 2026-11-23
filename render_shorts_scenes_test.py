import glob
import hashlib
import json
import os
import subprocess
import sys
import time
import numpy as np
import requests
from scipy.io.wavfile import write as write_wav

FPS = 30
WIDTH, HEIGHT = 720, 1280
SCALE = 1.5
IN_DIR = "render_input"
OUT_DIR = "clips"
HF_ROUTER_BASE = "https://router.huggingface.co/hf-inference/models"

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


def create_fallback_sfx(prompt_text, output_wav="fallback_sfx.wav", duration_sec=0.8, sr=22050):
  """API না পাওয়া গেলে প্রম্পটের ধরন অনুযায়ী শর্ট সিন্থেসাইজড SFX তৈরি করে।"""
  t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
  p = prompt_text.lower()
  if any(k in p for k in ["cannon", "boom", "impact", "explosion", "fire"]):
    # Low thump + filtered noise burst
    noise = np.random.normal(0, 1, len(t))
    env = np.exp(-6.0 * t)
    sub = np.sin(2 * np.pi * (85 * np.exp(-3.0 * t) + 35) * t)
    wave = (0.6 * sub + 0.5 * noise) * env
  elif any(k in p for k in ["sword", "clash", "metal", "swoosh", "whoosh"]):
    # Swept tone + metallic shimmer
    freq = 600 + 1800 * np.sin(np.pi * t / duration_sec)
    env = np.sin(np.pi * np.clip(t / duration_sec, 0, 1)) ** 1.5
    wave = (0.5 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2.41 * t)) * env
  else:
    # Subtle cinematic cue
    env = np.exp(-4.5 * t)
    wave = 0.4 * np.sin(2 * np.pi * 220 * t) * env

  peak = np.max(np.abs(wave)) or 1.0
  audio_int16 = np.int16(np.clip(wave / peak * 0.5, -1.0, 1.0) * 32767)
  write_wav(output_wav, sr, audio_int16)
  return output_wav


def fetch_or_synthesize_sfx(prompt_text, headers, output_mp3="temp_sfx.mp3"):
  from pydub import AudioSegment

  api_url = f"{HF_ROUTER_BASE}/cvssp/audioldm-m-full"
  if headers.get("Authorization"):
    for attempt in range(2):
      try:
        res = requests.post(
            api_url, headers=headers, json={"inputs": prompt_text}, timeout=60
        )
        ctype = res.headers.get("Content-Type", "")
        if res.status_code == 200 and ("audio" in ctype or len(res.content) > 2000):
          with open(output_mp3, "wb") as f:
            f.write(res.content)
          return True
        if res.status_code == 503:
          time.sleep(10)
        else:
          break
      except Exception as e:
        print(f"SFX API attempt {attempt + 1} error: {e}", flush=True)
        time.sleep(3)

  try:
    wav_file = create_fallback_sfx(prompt_text, "fallback_sfx.wav")
    AudioSegment.from_wav(wav_file).export(output_mp3, format="mp3")
    return True
  except Exception as e:
    print(f"Fallback SFX failed: {e}", flush=True)
    return False


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

    # --- AUTOMATIC SFX GENERATION & MIXING ---
    try:
      sfx_json = page.evaluate(
          "() => document.getElementById('sfx-data') ?"
          " document.getElementById('sfx-data').textContent : '[]'"
      )
      sfx_list = json.loads(sfx_json)

      if sfx_list and os.path.exists(audio):
        main_audio = AudioSegment.from_file(audio)
        hf_token = os.environ.get("HF_TOKEN", "").strip()
        headers = (
            {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}
            if hf_token
            else {}
        )

        for sfx in sfx_list:
          time_ms = int(sfx.get("time_ms", 0))
          prompt = sfx.get("prompt", "")
          print(f"Auto-generating SFX: '{prompt}' at {time_ms}ms", flush=True)

          if fetch_or_synthesize_sfx(prompt, headers, "temp_sfx.mp3"):
            try:
              new_sfx = AudioSegment.from_file("temp_sfx.mp3")[:2000] - 2
              main_audio = main_audio.overlay(new_sfx, position=time_ms)
              print(f"Applied SFX '{prompt}' at {time_ms}ms", flush=True)
            except Exception as mix_err:
              print(f"Error mixing SFX '{prompt}': {mix_err}", flush=True)

        main_audio.export(audio, format="mp3")
        print("Auto SFX processing complete!", flush=True)
    except Exception as e:
      print(f"Auto SFX skipped/failed globally: {e}", flush=True)
    # ---------------------------------------

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
    raise SystemExit("usage: render_shorts_scenes.py render N | merge")
