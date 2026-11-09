import os
import json

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TOTAL_CHUNKS = 10
WIDTH, HEIGHT = 1280, 720


def build_cartoon_rigging_prompt(scene_text, duration):
    return f"""
You are a master 2D Vector Cartoon Animator (like Kurzgesagt / Oversimplified / Adobe Animate).
Build a complete, self-contained HTML5 document (`<!DOCTYPE html>`) that plays a rich, colorful 2D rigged cartoon animation for this historical narration:

Narration: "{scene_text}"
Target Duration: {duration} seconds
Viewport Size: {WIDTH}x{HEIGHT} pixels

STRICT 2D CARTOON VISUAL & RIGGING RULES:
1. NO STICKMEN! Draw full-bodied, colorful 2D flat-vector cartoon characters using layered `<svg>` groups (`<g>`).
   - Every character MUST have: colored torso/tunic/armor (`<path>` or `<rect rx="...">`), expressive head with skin tone, eyes, eyebrows, headgear (crown, turban, helmet, hat), and separate articulated limbs (`<g class="arm-left">`, `<g class="arm-right">`, `<g class="leg-left">`, `<g class="leg-right">`) holding props (swords, shields, scrolls, muskets, flags).
2. ARTICULATED LIMB RIGGING (CSS Keyframes):
   - Use `transform-box: fill-box; transform-origin: top center;` on arms and legs so they swing naturally from the shoulders/hips!
   - Animate walking cycles, sword swinging, horse galloping, ship rocking, and flag waving using continuous CSS `@keyframes` (`infinite alternate ease-in-out`).
3. LAYERED PARALLAX ENVIRONMENT:
   - Rich multi-layered SVG background: animated sky gradient, drifting clouds, distant mountains/palaces/fortresses, mid-ground trees/rivers/ships, and foreground terrain.
   - Apply a slow cinematic camera pan or zoom on the master `<svg>` stage across {duration} seconds.
4. HTML5 CANVAS ATMOSPHERIC OVERLAY:
   - Include a transparent `<canvas>` overlay on top of the SVG driven by `window.updateSceneTime(t_ms)` to draw dynamic particles (floating embers, dust motes, rain, cannon smoke, or sunbeams) so every single frame is alive.
5. SYNCHRONIZED CLOCK HOOK (CRITICAL FOR RENDERER):
   - Define `window.updateSceneTime = function(t_ms) {{ ... }}` that updates both the `<canvas>` particles AND any JS-driven character movements deterministically based on `t_ms` (milliseconds from 0 to {int(duration*1000)}).
   - Also use standard CSS `@keyframes` for limb rigging and movement.
6. Output ONLY valid HTML inside a ```html ... ``` code block.
""".strip()


def main():
    from faster_whisper import WhisperModel
    from pydub import AudioSegment

    os.makedirs(OUT, exist_ok=True)
    print(f"Loading {AUDIO_FILE} ...", flush=True)
    audio = AudioSegment.from_file(AUDIO_FILE)
    total = len(audio) / 1000.0
    chunk_dur = total / TOTAL_CHUNKS

    print("Transcribing with Faster-Whisper ...", flush=True)
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments = list(model.transcribe(AUDIO_FILE)[0])

    meta, combined = [], []
    for i in range(TOTAL_CHUNKS):
        start = round(i * chunk_dur, 2)
        end = round((i + 1) * chunk_dur if i < TOTAL_CHUNKS - 1 else total, 2)

        texts = [
            s.text.strip() for s in segments
            if start <= (s.start + s.end) / 2 < end
        ]
        text = " ".join(texts).strip() or f"Historical Era Progression Part {i+1}"
        duration = round(max(end - start, 2.0), 2)

        audio[int(start * 1000):int(end * 1000)].export(f"{OUT}/audio_{i}.mp3", format="mp3")

        prompt = build_cartoon_rigging_prompt(text, duration)
        with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
        combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

        meta.append({"index": i, "duration": duration, "text": text})
        print(f"Chunk {i}: {duration}s | {text[:60]}...", flush=True)

    with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(combined))
    with open(f"{OUT}/chunks.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Done: {OUT}/", flush=True)


if __name__ == "__main__":
    main()
