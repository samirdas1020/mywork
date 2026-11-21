import glob
import hashlib
import json
import os
import subprocess
import sys

import sfx_engine  # dynamic SFX + music (numpy)

FPS = 30  # চাইলে 30 দিতে পারেন আরও স্মুথ অ্যানিমেশনের জন্য
WIDTH, HEIGHT = 1280, 720
SCALE = 1.5  # 1280x720 ক্যানভাসকে সরাসরি 1920x1080 (Full HD) হিসেবে রেন্ডার করবে
IN_DIR = "render_input"  # scene_N.html, audio_N.mp3, chunks.json
OUT_DIR = "clips"
SFX = os.environ.get("RENDER_SFX", "1") != "0"  # scene-driven sound effects
MUSIC = os.environ.get("RENDER_MUSIC", "1") != "0"  # scene-driven background music (merge step)

# Freeze every kind of animation at time t, then let the page draw that moment.
STEP_JS = """t => {
  document.getAnimations().forEach(a => {
    try { a.pause(); a.currentTime = t; } catch (e) {}
  });
  document.querySelectorAll('svg').forEach(s => {
    try { s.pauseAnimations(); s.setCurrentTime(t / 1000); } catch (e) {}
  });
  if (window.updateSceneTime) window.updateSceneTime(t);
}"""

# Stop the page's own real-time loops so they cannot overwrite our frame.
INIT_JS = """
window.requestAnimationFrame = () => 0;
window.setInterval = () => 0;
window.setTimeout = () => 0;
"""


def render(i):
  from playwright.sync_api import sync_playwright

  with open(f"{IN_DIR}/chunks.json", encoding="utf-8") as f:
    meta = {c["index"]: c for c in json.load(f)}

  duration = float(meta[i]["duration"])
  frames = max(1, round(duration * FPS))

  scene = os.path.abspath(f"{IN_DIR}/scene_{i}.html")
  audio = f"{IN_DIR}/audio_{i}.mp3"
  os.makedirs(OUT_DIR, exist_ok=True)
  video = f"{OUT_DIR}/video_{i}.mp4"
  final = f"{OUT_DIR}/synced_{i}.mp4"

  print(
      f"Chunk {i}: {duration}s, {frames} frames"
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

    events, colors = [], []
    if SFX:
      try:  # step the scene without screenshots and find what happens when
        events = sfx_engine.find_events(page, STEP_JS, frames, FPS)
        print(f"  SFX: {len(events)} events found", flush=True)
      except Exception as ex:
        print("SFX analysis skipped:", ex, flush=True)
      page.goto("file://" + scene, wait_until="load")  # fresh page for the real render
      page.wait_for_timeout(500)

    for f in range(frames):
      t = f * 1000.0 / FPS
      page.evaluate(STEP_JS, t)
      img = page.screenshot(type="jpeg", quality=95)
      ff.stdin.write(img)
      if f % 5 == 0:
        seen.add(hashlib.md5(img).hexdigest())
      if SFX and f % 15 == 0:
        colors.append(sfx_engine.sample_color(img))
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

  if SFX:
    mixed = sfx_engine.mix_chunk(
        events, frames, FPS, audio if os.path.exists(audio) else None
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video,
            "-f", "f32le", "-ar", str(sfx_engine.SR), "-ac", "2", "-i", "-",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            final,
        ],
        input=mixed.tobytes(),
        check=True,
    )
    os.remove(video)
    sfx_engine.save_meta(f"{OUT_DIR}/sfx_{i}.json", events, colors, duration)
  elif os.path.exists(audio):
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
    os.remove(video)  # ডিস্ক স্পেস বাঁচাতে অস্থায়ী ভিডিও ফাইল মুছে ফেলা
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

  has_meta = SFX and any(
      os.path.exists(f"{OUT_DIR}/sfx_{os.path.basename(p).split('_')[1].split('.')[0]}.json")
      for p in files
  )
  out = "final_video.mp4"
  tmp = f"{OUT_DIR}/concat_tmp.mp4" if has_meta else out
  subprocess.run(
      [
          "ffmpeg", "-y", "-loglevel", "error",
          "-f", "concat", "-safe", "0", "-i", "concat.txt",
          "-c:v", "copy",
      ] + (["-an"] if has_meta else ["-c:a", "aac", "-b:a", "192k"]) + [
          "-movflags", "+faststart",
          tmp,
      ],
      check=True,
  )

  if has_meta:
    # sample-exact voice track: each clip's audio is decoded alone and fitted to its video length
    durs = sfx_engine.join_voice(files, f"{OUT_DIR}/voice_all.wav")
    if MUSIC:
      cuts, accents, times, feats = sfx_engine.collect(OUT_DIR, files, durs)
      bgm, info = sfx_engine.make_music(sum(durs) + 0.5, cuts, accents, times, feats)
      print(f"Music: {info['bpm']} BPM, {'minor' if info['minor'] else 'major'}", flush=True)
      sfx_engine.write_wav(f"{OUT_DIR}/bgm.wav", bgm)
      subprocess.run(
          [
              "ffmpeg", "-y", "-loglevel", "error",
              "-i", tmp, "-i", f"{OUT_DIR}/voice_all.wav", "-i", f"{OUT_DIR}/bgm.wav",
              "-filter_complex",
              "[1:a]asplit=2[vo][sc];[2:a]volume=0.28[bg];"
              "[bg][sc]sidechaincompress=threshold=0.04:ratio=8:attack=15:release=350[duck];"
              "[vo][duck]amix=inputs=2:duration=first[m];"
              "[m]loudnorm=I=-14:TP=-1.5:LRA=11,asoftclip=type=tanh:threshold=0.85[a]",
              "-map", "0:v", "-map", "[a]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
              "-movflags", "+faststart", out,
          ],
          check=True,
      )
    else:  # sound effects only: same sample-exact voice track, no music, no loudness change
      subprocess.run(
          [
              "ffmpeg", "-y", "-loglevel", "error",
              "-i", tmp, "-i", f"{OUT_DIR}/voice_all.wav",
              "-map", "0:v", "-map", "1:a",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
              "-movflags", "+faststart", out,
          ],
          check=True,
      )
    os.remove(tmp)
  print(f"Merged {len(files)} clips -> {out}", flush=True)


if __name__ == "__main__":
  mode = sys.argv[1]
  if mode == "render":
    render(int(sys.argv[2]))
  elif mode == "merge":
    merge()
  else:
    raise SystemExit("usage: render_scenes.py render N | merge")
