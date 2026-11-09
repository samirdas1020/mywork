import json
import os
import shutil

from auto_animator import build_cartoon_rigging_prompt, WORKSPACE

OUT = "prompts_output"

os.makedirs(OUT, exist_ok=True)

with open(f"{WORKSPACE}/chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

combined = []
for c in chunks:
    i = c["index"]
    prompt = build_cartoon_rigging_prompt(c["text"], c["duration"]).strip()

    with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    shutil.copy(f"{WORKSPACE}/audio_{i}.mp3", f"{OUT}/audio_{i}.mp3")

    combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(combined))

shutil.copy(f"{WORKSPACE}/chunks.json", f"{OUT}/chunks.json")
print(f"Done: {len(chunks)} prompts created in {OUT}/")
