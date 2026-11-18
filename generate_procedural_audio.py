import json
import os
import re
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SAMPLE_RATE = 44100


def butter_bandpass(lowcut, highcut, fs, order=3):
    nyq = 0.5 * fs
    low = max(0.001, min(lowcut / nyq, 0.99))
    high = max(low + 0.001, min(highcut / nyq, 0.999))
    b, a = butter(order, [low, high], btype='band')
    return b, a


def butter_lowpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    normal_cutoff = max(0.001, min(cutoff / nyq, 0.999))
    b, a = butter(order, normal_cutoff, btype='low')
    return b, a


def butter_highpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    normal_cutoff = max(0.001, min(cutoff / nyq, 0.999))
    b, a = butter(order, normal_cutoff, btype='high')
    return b, a


def normalize_and_fade(wave, volume=0.6, fade_in=0.015, fade_out=0.04):
    if len(wave) == 0:
        return wave
    peak = np.max(np.abs(wave))
    if peak > 1e-6:
        wave = wave / peak
    n = len(wave)
    fi = min(n // 3, int(fade_in * SAMPLE_RATE))
    fo = min(n // 3, int(fade_out * SAMPLE_RATE))
    if fi > 0:
        wave[:fi] *= np.linspace(0, 1, fi)
    if fo > 0:
        wave[-fo:] *= np.linspace(1, 0, fo)
    return wave * volume


def sfx_dramatic_hit(duration_sec=1.3, volume=0.85):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    freq = 28 + 130 * np.exp(-t * 7.5)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.tanh(2.5 * np.sin(phase)) * np.exp(-t * 2.5)
    snap = np.random.normal(0, 1, n) * np.exp(-t * 28.0)
    b, a = butter_bandpass(400, 3200, SAMPLE_RATE, order=2)
    snap = lfilter(b, a, snap)
    return normalize_and_fade(sub + 0.45 * snap, volume=volume, fade_in=0.002, fade_out=0.08)


def sfx_destruction_crumble(duration_sec=1.8, volume=0.78):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    rumble = np.random.normal(0, 1, n)
    b_lo, a_lo = butter_lowpass(320, SAMPLE_RATE, order=3)
    rumble = lfilter(b_lo, a_lo, rumble) * np.exp(-t * 1.4)

    debris = np.zeros(n)
    for _ in range(36):
        pos = np.random.randint(0, max(1, n - 700))
        chunk = np.random.normal(0, 1, 700) * np.exp(-np.linspace(0, 14, 700))
        debris[pos:pos + 700] += chunk
    b_hi, a_hi = butter_bandpass(800, 4200, SAMPLE_RATE, order=2)
    debris = lfilter(b_hi, a_hi, debris) * np.exp(-t * 1.2)
    return normalize_and_fade(1.2 * rumble + 0.8 * debris, volume=volume, fade_in=0.01, fade_out=0.12)


def sfx_sword_battle(duration_sec=0.85, volume=0.75):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    freqs = [1380, 2150, 3290, 4750, 6100]
    clang = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (5.5 + i * 2.0)) for i, f in enumerate(freqs))
    scrape = np.random.normal(0, 1, n) * np.exp(-t * 25.0)
    b, a = butter_highpass(1800, SAMPLE_RATE, order=2)
    scrape = lfilter(b, a, scrape)
    return normalize_and_fade(clang + 0.55 * scrape, volume=volume, fade_in=0.003, fade_out=0.06)


def sfx_dig_earth(duration_sec=0.45, volume=0.72):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    thud = np.sin(2 * np.pi * (42 + 95 * np.exp(-t * 22)) * t) * np.exp(-t * 15)
    dirt = np.random.normal(0, 1, n) * np.exp(-t * 9.5)
    b, a = butter_bandpass(450, 2800, SAMPLE_RATE, order=2)
    dirt = lfilter(b, a, dirt)
    return normalize_and_fade(thud + 0.85 * dirt, volume=volume, fade_in=0.004, fade_out=0.05)


def sfx_fire_burst(duration_sec=1.2, volume=0.68):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    flame = np.random.normal(0, 1, n)
    b, a = butter_bandpass(180, 1400, SAMPLE_RATE, order=2)
    flame = lfilter(b, a, flame) * np.sin(np.pi * (t / duration_sec))
    crackles = (np.random.rand(n) > 0.996).astype(np.float32) * np.random.normal(0, 4.0, n)
    return normalize_and_fade(flame + crackles, volume=volume, fade_in=0.05, fade_out=0.15)


def sfx_paper_map(duration_sec=0.65, volume=0.65):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(1500, 5800, SAMPLE_RATE, order=2)
    paper = lfilter(b, a, noise) * (0.5 + 0.5 * np.sin(2 * np.pi * 12 * t))
    return normalize_and_fade(paper, volume=volume, fade_in=0.02, fade_out=0.06)


def sfx_thunder_storm(duration_sec=2.2, volume=0.82):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    crack = np.random.normal(0, 1, n) * np.exp(-t * 14.0)
    rumble = np.random.normal(0, 1, n)
    b, a = butter_lowpass(220, SAMPLE_RATE, order=3)
    rumble = lfilter(b, a, rumble) * np.exp(-t * 1.1)
    return normalize_and_fade(0.7 * crack + 1.3 * rumble, volume=volume, fade_in=0.005, fade_out=0.2)


def sfx_water_splash(duration_sec=1.1, volume=0.65):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(350, 2400, SAMPLE_RATE, order=2)
    water = lfilter(b, a, noise) * np.sin(np.pi * (t / duration_sec))
    return normalize_and_fade(water, volume=volume, fade_in=0.06, fade_out=0.15)


def sfx_riser_tension(duration_sec=1.2, volume=0.58):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    freq = 110 + 480 * ((t / duration_sec) ** 2)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    tone = np.sin(phase) * ((t / duration_sec) ** 1.8)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(400, 2800, SAMPLE_RATE, order=2)
    whoosh = lfilter(b, a, noise) * ((t / duration_sec) ** 2.2)
    return normalize_and_fade(0.6 * tone + 0.7 * whoosh, volume=volume, fade_in=0.08, fade_out=0.02)


def sfx_ui_pop(duration_sec=0.12, volume=0.55):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    freq = 320 + 680 * np.exp(-t * 42)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    return normalize_and_fade(np.sin(phase) * np.exp(-t * 30), volume=volume, fade_in=0.002, fade_out=0.02)


def sfx_clock_tick(duration_sec=0.08, volume=0.52):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    click = np.sin(2 * np.pi * 2200 * t) + 0.7 * np.sin(2 * np.pi * 3900 * t)
    return normalize_and_fade(click * np.exp(-t * 75), volume=volume, fade_in=0.001, fade_out=0.01)


def sfx_soft_swoosh(duration_sec=0.35, volume=0.45):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(320, 1500, SAMPLE_RATE, order=2)
    filtered = lfilter(b, a, noise) * (np.sin(np.pi * (t / duration_sec)) ** 1.8)
    return normalize_and_fade(filtered, volume=volume, fade_in=0.02, fade_out=0.04)


def generate_ambience_bed(amb_type, duration_sec, volume=0.22):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)

    if amb_type == "fire":
        b, a = butter_bandpass(140, 1100, SAMPLE_RATE, order=2)
        bed = lfilter(b, a, noise) * (0.7 + 0.3 * np.sin(2 * np.pi * 2.1 * t))
        sparks = (np.random.rand(n) > 0.998).astype(np.float32) * np.random.normal(0, 3.0, n)
        bed += sparks
    elif amb_type == "water":
        b, a = butter_bandpass(250, 1600, SAMPLE_RATE, order=2)
        bed = lfilter(b, a, noise) * (0.65 + 0.35 * np.sin(2 * np.pi * 0.25 * t))
    elif amb_type == "crowd":
        b, a = butter_bandpass(300, 1300, SAMPLE_RATE, order=2)
        bed = lfilter(b, a, noise) * (0.75 + 0.25 * np.sin(2 * np.pi * 0.9 * t))
    else:
        b, a = butter_bandpass(180, 750, SAMPLE_RATE, order=2)
        bed = lfilter(b, a, noise) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.35 * t))

    return normalize_and_fade(bed, volume=volume, fade_in=0.3, fade_out=0.4)


def compose_dynamic_bgm(duration_sec, mood="suspense", volume=0.22):
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    roots = [82.41, 65.41, 73.42, 61.74] if mood == "action" else [73.42, 58.27, 49.00, 55.00]
    pulse_hz = 0.25 if mood == "action" else 0.5
    tempo_decay = 13.0 if mood == "action" else 10.0

    bass = np.zeros(n)
    pad = np.zeros(n)
    step_samples = int(4.0 * SAMPLE_RATE)

    for idx, start in enumerate(range(0, n, step_samples)):
        end = min(n, start + step_samples)
        seg_t = t[start:end]
        f0 = roots[idx % len(roots)]
        bass[start:end] = np.sin(2 * np.pi * f0 * seg_t) + 0.3 * np.sin(2 * np.pi * (f0 * 2) * seg_t)
        pad[start:end] = (
            0.4 * np.sin(2 * np.pi * (f0 * 4) * seg_t)
            + 0.3 * np.sin(2 * np.pi * (f0 * 4 * 1.189) * seg_t)
            + 0.3 * np.sin(2 * np.pi * (f0 * 6) * seg_t)
        )

    p_phase = (t % pulse_hz) / pulse_hz
    rhythm = np.exp(-p_phase * tempo_decay) * np.sin(2 * np.pi * 64.0 * t)

    raw_bgm = 0.55 * bass + 0.35 * pad + 0.50 * rhythm
    b_lp, a_lp = butter_lowpass(1350, SAMPLE_RATE, order=2)
    smooth_bgm = lfilter(b_lp, a_lp, raw_bgm)
    return normalize_and_fade(smooth_bgm, volume=volume, fade_in=0.5, fade_out=0.7)


def detect_sound_for_english_context(text_and_code, is_shot_start=False):
    s = text_and_code.lower()

    if re.search(r"\b(crumble|destroy|destroyed|temple|ruin|ruins|collapse|collapsed|earthquake|blast|explode|shake|shatter|demolish|razed|debris)\b", s):
        return "crumble"
    if re.search(r"\b(war|sword|swords|army|armies|battle|soldier|soldiers|emperor|roman|romans|shield|knife|clash|attack|fight|siege|legion|conquer|blood)\b", s):
        return "sword"
    if re.search(r"\b(dig|dug|shovel|pickaxe|excavate|excavation|bury|buried|dirt|hill|soil|earth|mound|tunnel|stone|build|built)\b", s):
        return "dig"
    if re.search(r"\b(fire|torch|flame|flames|burn|burned|burning|ash|ashes|smoke)\b|#ef4444|#f97316|#dc2626", s):
        return "fire"
    if re.search(r"\b(thunder|lightning|storm|sky|cloud|flash)\b", s):
        return "thunder"
    if re.search(r"\b(ocean|sea|river|water|wave|waves|rain|flood|boat|ship)\b", s):
        return "water"
    if re.search(r"\b(map|pin|route|scroll|jerusalem|book|page|document|letter|draw|path|line|location|city)\b", s):
        return "paper"
    if re.search(r"\b(clock|dial|century|centuries|year|years|timer|decade|decades|era|age|time)\b", s):
        return "tick"
    if re.search(r"\b(secret|mystery|hidden|unknown|clue|discover|discovered|treasure|tomb|church|holy|cross|truth|never|until)\b", s):
        return "riser"

    return "hit" if is_shot_start else "pop"


def build_timeline_from_html_and_script(html_path, chunk_idx, total_dur_sec):
    events = []
    ambiences = []

    html_code = ""
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

    clean_html = re.sub(r"<head>.*?</head>", "", html_code, flags=re.S | re.I)
    clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.S | re.I)

    narration_text = ""
    chunks_json = os.path.join(os.path.dirname(html_path), "chunks.json")
    if os.path.exists(chunks_json):
        try:
            with open(chunks_json, "r", encoding="utf-8") as f:
                for c in json.load(f):
                    if int(c.get("index", -1)) == int(chunk_idx):
                        narration_text = c.get("text", "")
                        break
        except Exception:
            pass

    full_text = (clean_html + " " + narration_text).lower()
    mood = "action" if re.search(r"\b(war|battle|attack|destroy|siege|army|fight|blood)\b", full_text) else "suspense"

    shot_cuts = [0.0]
    for m in re.finditer(r"t_ms\s*<\s*(\d+)", clean_html):
        sec = int(m.group(1)) / 1000.0
        if 0.6 < sec < total_dur_sec - 0.3:
            shot_cuts.append(sec)
    shot_cuts = sorted(list(set(shot_cuts)))
    shot_cuts.append(total_dur_sec)

    shot_blocks = re.split(r"if\s*\(\s*activeShot\s*===\s*\d+\s*\)", clean_html)

    for idx in range(len(shot_cuts) - 1):
        s_start = shot_cuts[idx]
        s_end = shot_cuts[idx + 1]
        s_dur = max(0.4, s_end - s_start)
        block = shot_blocks[idx + 1] if (idx + 1) < len(shot_blocks) else clean_html

        if idx > 0 and s_dur >= 1.5:
            events.append((max(0.0, s_start - 0.1), "swoosh"))

        snd = detect_sound_for_english_context(block, is_shot_start=True)
        events.append((s_start + 0.1, snd))

        if re.search(r"\b(fire|torch|flame|burn)\b", block, re.I):
            ambiences.append((s_start, s_end, "fire"))
        elif re.search(r"\b(water|sea|river|rain)\b", block, re.I):
            ambiences.append((s_start, s_end, "water"))
        elif re.search(r"\b(crowd|city|people|street|kingdom)\b", block, re.I):
            ambiences.append((s_start, s_end, "crowd"))
        else:
            ambiences.append((s_start, s_end, "wind"))

    # JS micro-events
    for m in re.finditer(r"\b(t_ms|t|time|elapsed)\s*(?:>=|>|===|==)\s*(\d+(?:\.\d+)?)", clean_html):
        var_name = m.group(1)
        val = float(m.group(2))
        sec = (val / 1000.0) if (var_name == "t_ms" or val > 60) else val
        if 0.2 < sec < total_dur_sec - 0.2:
            snippet = clean_html[m.end():m.end() + 300]
            snd = detect_sound_for_english_context(snippet, is_shot_start=False)
            events.append((sec, snd))

    # English narration sentence-by-sentence sync
    if narration_text.strip():
        sentences = [seg.strip() for seg in re.split(r"[.!?,;\n]+", narration_text) if len(seg.strip()) > 3]
        if sentences:
            step = total_dur_sec / len(sentences)
            for i, sent in enumerate(sentences):
                t_sent = i * step + 0.15
                if t_sent < total_dur_sec - 0.3:
                    snd = detect_sound_for_english_context(sent, is_shot_start=False)
                    if snd != "pop" or (i % 2 == 0):
                        events.append((t_sent, snd))

    events.sort(key=lambda x: x[0])
    final_events = []
    last_t = -999.0
    for t_sec, snd in events:
        if (t_sec - last_t) >= 0.45:
            final_events.append((t_sec, snd))
            last_t = t_sec

    return final_events, ambiences, mood


def mix_segment(target_track, wave, start_sec):
    start_idx = int(start_sec * SAMPLE_RATE)
    if start_idx >= len(target_track) or start_idx < 0:
        return
    end_idx = min(len(target_track), start_idx + len(wave))
    target_track[start_idx:end_idx] += wave[:end_idx - start_idx]


def build_clip_audio(html_path, voice_mp3_path, output_wav_path):
    m = re.search(r"scene[_-](\d+)\.html", os.path.basename(html_path))
    chunk_idx = int(m.group(1)) if m else 0

    temp_voice_wav = output_wav_path + ".voice_tmp.wav"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", voice_mp3_path,
        "-ar", str(SAMPLE_RATE), "-ac", "1",
        temp_voice_wav
    ], check=True)

    sr, voice_data = wavfile.read(temp_voice_wav)
    os.remove(temp_voice_wav)

    voice = voice_data.astype(np.float32) / 32768.0
    total_dur = len(voice) / SAMPLE_RATE

    events, ambiences, mood = build_timeline_from_html_and_script(html_path, chunk_idx, total_dur)

    bgm = compose_dynamic_bgm(total_dur, mood=mood, volume=0.22)
    voice_env = np.convolve(np.abs(voice), np.ones(int(SAMPLE_RATE * 0.25)) / (SAMPLE_RATE * 0.25), mode='same')
    ducking = np.where(voice_env > 0.015, 0.62, 1.0)
    bgm = bgm * ducking

    ambience_track = np.zeros_like(voice)
    for a_start, a_end, a_type in ambiences:
        seg_dur = max(0.2, a_end - a_start)
        mix_segment(ambience_track, generate_ambience_bed(a_type, seg_dur, volume=0.22), a_start)

    sfx_track = np.zeros_like(voice)
    sfx_bank = {
        "hit": sfx_dramatic_hit(),
        "crumble": sfx_destruction_crumble(),
        "sword": sfx_sword_battle(),
        "dig": sfx_dig_earth(),
        "fire": sfx_fire_burst(),
        "thunder": sfx_thunder_storm(),
        "water": sfx_water_splash(),
        "paper": sfx_paper_map(),
        "tick": sfx_clock_tick(),
        "riser": sfx_riser_tension(),
        "swoosh": sfx_soft_swoosh(),
        "pop": sfx_ui_pop(),
    }

    for t_sec, snd in events:
        if snd in sfx_bank:
            mix_segment(sfx_track, sfx_bank[snd], t_sec)

    mixed = (voice * 1.0) + (sfx_track * 0.90) + (ambience_track * 0.85) + bgm
    mixed = np.tanh(mixed * 0.95)

    final_int16 = np.int16(np.clip(mixed, -1.0, 1.0) * 32767)
    wavfile.write(output_wav_path, SAMPLE_RATE, final_int16)

    summary = ", ".join([f"{round(t,1)}s:{s}" for t, s in events[:12]])
    print(f"Generated scene audio [{mood}]: {output_wav_path} | Events({len(events)}): [{summary}]", flush=True)
