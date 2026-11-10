import os
import json

AUDIO_FILE = "input_audio.mp3"
OUT = "prompts_output"
TOTAL_CHUNKS = 10
WIDTH, HEIGHT = 1280, 720


def build_cartoon_rigging_prompt(scene_text, duration, timeline=""):
    return f"""
You are a master 2D Vector Cartoon Animator (like Kurzgesagt / Oversimplified / Adobe Animate).
Build a complete, self-contained HTML5 document (`<!DOCTYPE html>`) that plays a rich, colorful 2D rigged cartoon animation for this historical narration:

Narration: "{scene_text}"
Target Duration: {duration} seconds
Timed narration (seconds from the start of this clip; this is exactly when each sentence is spoken):
{timeline}
Viewport Size: {WIDTH}x{HEIGHT} pixels

STRICT 2D CARTOON VISUAL & RIGGING RULES:
1. NO STICKMEN! Draw full-bodied, colorful 2D flat-vector cartoon characters using layered `<svg>` groups (`<g>`).
   - Every MAIN character (the few people the sentence is really about) MUST have: colored torso/tunic/armor (`<path>` or `<rect rx="...">`), expressive head with skin tone, eyes, eyebrows, headgear (crown, turban, helmet, hat), and separate articulated limbs (`<g class="arm-left">`, `<g class="arm-right">`, `<g class="leg-left">`, `<g class="leg-right">`) holding props that fit the story. Background crowd figures stay simple (head, body, legs).
   - Choose clothes, headgear, tools, weapons, buildings, vehicles, skin tones and landscape that match the ERA, REGION and CULTURE named in the narration (for example robes and temples for ancient Egypt, longships for Vikings, muskets and flags for 1800s Europe). Never fall back on a default look such as Roman soldiers in a desert.
2. ARTICULATED LIMB RIGGING (CSS Keyframes):
   - Rotate arms and legs around the shoulder/hip joint using the absolute px `transform-origin` described below (do NOT use `fill-box` or `top center`, they pivot at the wrong point).
   - Animate walking cycles, sword swinging, horse galloping, ship rocking, and flag waving using continuous CSS `@keyframes` (`infinite alternate ease-in-out`).
   - LIMB ATTACHMENT (CRITICAL): every arm and leg must stay attached to the body while moving. Set `transform-origin` in absolute px (e.g. `transform-origin: 28px 40px`) exactly at the shoulder or hip joint, and make the top end of each limb overlap INTO the torso by a few pixels so no gap is ever visible.
   - WALK CYCLE: opposite limbs move together (left arm with right leg, right arm with left leg) using the same duration and timing, with a small body up/down bob in the same rhythm. Never animate limbs with unrelated speeds.
3. LAYERED PARALLAX ENVIRONMENT:
   - Rich multi-layered SVG background that matches the place and time in the narration (desert, sea, forest, snow, city, palace, battlefield, farmland, etc.): sky colours for the right time of day and weather, distant scenery, mid-ground objects, and foreground terrain.
   - Apply a slow cinematic camera pan or zoom on the master `<svg>` stage across {duration} seconds.
4. HTML5 CANVAS ATMOSPHERIC OVERLAY:
   - Include a transparent `<canvas>` overlay on top of the SVG driven by `window.updateSceneTime(t_ms)` to draw dynamic particles (floating embers, dust motes, rain, cannon smoke, or sunbeams) so every single frame is alive.
5. SYNCHRONIZED CLOCK HOOK (CRITICAL FOR RENDERER):
   - Define `window.updateSceneTime = function(t_ms) {{ ... }}` that updates both the `<canvas>` particles AND any JS-driven character movements deterministically based on `t_ms` (milliseconds from 0 to {int(duration*1000)}).
   - Also use standard CSS `@keyframes` for limb rigging and movement.
6. NEVER use `<use>` or `<symbol>`, because animations inside `<use>` cannot be frame-synced. Main characters are written out in full with their own limb groups. Crowds and armies must be created by a JS loop at load time using `document.createElementNS` (each figure a few simple shapes: head circle, body, legs), placed with a seeded pseudo-random function so the layout is always identical, and moved only from `window.updateSceneTime(t_ms)`.
7. CHARACTERS MUST STAND ON THE GROUND: keep every character upright (never rotate a whole character group). On slopes, stairs or ships, only move characters with translate so their feet touch the surface. Characters must not overlap each other or float in the air.
8. TIMING & SCENES FOLLOW THE TIMED NARRATION: the animation length is exactly {duration} seconds ({int(duration*1000)} ms). Use this exact value everywhere; do not loop.
   - Make one scene per timed sentence above (merge a sentence shorter than 3 seconds into its neighbour). A scene must start exactly at that sentence's start time and end at its end time, so the picture always matches what is being said right now.
   - Build each scene as its own `<g class="scene" id="scene-N">`. Inside `window.updateSceneTime(t_ms)` show only the active scene (opacity/display) based on `t_ms`, with a quick 0.4 second cross-fade between scenes. Every scene needs a different location, camera angle or action; never repeat the same picture.
9. DETERMINISTIC ONLY: do NOT use requestAnimationFrame, setInterval, setTimeout, Date.now or performance.now. Any JS motion must be computed only from the `t_ms` given to `window.updateSceneTime`. Math.random is allowed only once at start to create particle seeds.
10. NEVER use CSS `transition` or JS-driven animations for opacity/position (they run in real time and break frame capture). Set opacity, display and transforms only from `window.updateSceneTime(t_ms)`. CSS `@keyframes` is allowed only for limb/loop movement.
11. CAMERA: when panning or zooming the stage, never expose its edges. Draw backgrounds wider than 1280x720 and keep translate smaller than (scale-1)*640 horizontally.
12. Short on-screen labels ARE allowed and encouraged for numbers, years, place names and who is who, copied from the narration (for example the army size, the year, the city or the person's name): at most 4 words each, in clear large text. Do NOT write full sentences, subtitles or captions of the narration.
13. Output ONLY valid HTML inside a ```html ... ``` code block, with no explanation before or after.
""".strip()


def build_timeline(segments, start, end):
    """Sentence lines with times relative to the chunk start."""
    lines = []
    for sg in segments:
        mid = (sg.start + sg.end) / 2
        if start <= mid < end:
            a = max(sg.start - start, 0.0)
            b = min(sg.end - start, end - start)
            lines.append(f"[{a:.1f}s - {b:.1f}s] {sg.text.strip()}")
    return "\n".join(lines)


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

        timeline = build_timeline(segments, start, end) or f"[0.0s - {duration:.1f}s] {text}"
        prompt = build_cartoon_rigging_prompt(text, duration, timeline)
        with open(f"{OUT}/prompt_{i}.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
        combined.append(f"===== PROMPT {i} =====\n{prompt}\n")

        meta.append({"index": i, "duration": duration, "text": text, "timeline": timeline})
        print(f"Chunk {i}: {duration}s | {text[:60]}...", flush=True)

    with open(f"{OUT}/all_prompts.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(combined))
    with open(f"{OUT}/chunks.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Done: {OUT}/", flush=True)


if __name__ == "__main__":
    main()
