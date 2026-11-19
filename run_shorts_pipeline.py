import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

PROMPTS_DIR = "prompts_output"
RENDER_IN_DIR = "render_input"
CLIPS_DIR = "clips"
RENDER_SCRIPT = "render_shorts_scenes.py"


def sync_inputs(prompts_dir=PROMPTS_DIR, render_in_dir=RENDER_IN_DIR):
  chunks_src = os.path.join(prompts_dir, "chunks.json")
  if not os.path.exists(chunks_src):
    raise SystemExit(
        f"Missing {chunks_src}. Run prepare_shorts_prompts.py first."
    )

  os.makedirs(render_in_dir, exist_ok=True)
  shutil.copy2(chunks_src, os.path.join(render_in_dir, "chunks.json"))

  # Copy audio_N.mp3 files from prompts_output to render_input
  for audio_path in glob.glob(os.path.join(prompts_dir, "audio_*.mp3")):
    shutil.copy2(
        audio_path, os.path.join(render_in_dir, os.path.basename(audio_path))
    )

  # Normalize scene-N.html -> scene_N.html inside render_input
  for hyphen_html in glob.glob(os.path.join(render_in_dir, "scene-*.html")):
    m = re.search(r"scene-(\d+)\.html$", os.path.basename(hyphen_html))
    if m:
      target_html = os.path.join(render_in_dir, f"scene_{m.group(1)}.html")
      if not os.path.exists(target_html):
        os.rename(hyphen_html, target_html)

  with open(chunks_src, encoding="utf-8") as f:
    chunks = json.load(f)

  indices = []
  for pos, item in enumerate(chunks):
    indices.append(int(item.get("index", pos)))
  return sorted(indices)


def get_missing_scenes(indices, render_in_dir=RENDER_IN_DIR):
  missing = []
  for idx in indices:
    scene_underscore = os.path.join(render_in_dir, f"scene_{idx}.html")
    scene_hyphen = os.path.join(render_in_dir, f"scene-{idx}.html")
    if not (os.path.exists(scene_underscore) or os.path.exists(scene_hyphen)):
      missing.append(idx)
  return missing


def run_render_chunk(idx, render_script=RENDER_SCRIPT):
  subprocess.run([sys.executable, render_script, "render", str(idx)], check=True)


def run_merge(render_script=RENDER_SCRIPT):
  subprocess.run([sys.executable, render_script, "merge"], check=True)


def main():
  parser = argparse.ArgumentParser(
      description="Sync prompts_output -> render_input, render all clips, and merge."
  )
  parser.add_argument(
      "--only",
      type=str,
      default="",
      help="Optional comma-separated chunk indices to render, e.g. 0,1,2",
  )
  parser.add_argument(
      "--skip-missing",
      action="store_true",
      help="Skip chunks whose scene_N.html is missing instead of stopping.",
  )
  parser.add_argument(
      "--no-merge",
      action="store_true",
      help="Render chunks without running final merge.",
  )
  args = parser.parse_args()

  if not os.path.exists(RENDER_SCRIPT):
    raise SystemExit(f"Missing {RENDER_SCRIPT} in current directory.")

  all_indices = sync_inputs(PROMPTS_DIR, RENDER_IN_DIR)
  if not all_indices:
    raise SystemExit("No chunks found in chunks.json.")

  if args.only.strip():
    target_indices = [
        int(x.strip()) for x in args.only.split(",") if x.strip().isdigit()
    ]
  else:
    target_indices = all_indices

  missing = get_missing_scenes(target_indices, RENDER_IN_DIR)
  if missing and not args.skip_missing:
    print(
        f"Missing HTML scene files for chunk(s): {missing} inside"
        f" '{RENDER_IN_DIR}/'.",
        flush=True,
    )
    print(
        "Generate scene_N.html from prompts_output/prompt_N.txt and place them"
        f" in '{RENDER_IN_DIR}/' (or run with --skip-missing).",
        flush=True,
    )
    raise SystemExit(1)

  rendered_any = False
  for idx in target_indices:
    scene_path = os.path.join(RENDER_IN_DIR, f"scene_{idx}.html")
    if not os.path.exists(scene_path):
      print(
          f"Skipping chunk {idx}: {scene_path} not found.", flush=True
      )
      continue
    run_render_chunk(idx, RENDER_SCRIPT)
    rendered_any = True

  if not args.no_merge:
    if rendered_any or glob.glob(os.path.join(CLIPS_DIR, "synced_*.mp4")):
      run_merge(RENDER_SCRIPT)
    else:
      print("Nothing rendered to merge.", flush=True)


if __name__ == "__main__":
  main()
