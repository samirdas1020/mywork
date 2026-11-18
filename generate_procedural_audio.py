import json
import os
import re
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SAMPLE_RATE = 44100


# ==============================================================================
# ১. অডিও ফিল্টার হেল্পার
# ==============================================================================
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


def normalize_and_fade(wave, volume=0.5, fade_in=0.02, fade_out=0.05):
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


# ==============================================================================
# ২. ইউনিভার্সাল প্যারামেট্রিক সাউন্ড সিন্থেসিস কোর (৪টি মৌলিক ফিজিক্স ইঞ্জিন)
# ==============================================================================
def engine_impact(freq_start, freq_end, decay, noise_mix=0.3, distortion=1.5, duration_sec=1.2, volume=0.7):
    """বিস্ফোরণ, গুলি, বজ্রপাত, ভূমিকম্প বা নাটকীয় ধাক্কার ফিজিক্স ইঞ্জিন"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    freq = freq_end + (freq_start - freq_end) * np.exp(-t * (decay * 2.5))
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    body = np.tanh(distortion * np.sin(phase)) * np.exp(-t * decay)

    noise = np.random.normal(0, 1, n)
    b, a = butter_lowpass(1200, SAMPLE_RATE, order=2)
    blast = lfilter(b, a, noise) * np.exp(-t * (decay * 1.4))

    raw = (1.0 - noise_mix) * body + noise_mix * blast
    return normalize_and_fade(raw, volume=volume, fade_in=0.003, fade_out=0.1)


def engine_texture(low_hz, high_hz, duration_sec, mod_freq=0.5, crackle_rate=0.0, volume=0.25):
    """বৃষ্টি, বাতাস, আগুন, সমুদ্রের ঢেউ, ভিড় বা কাগজের টেক্সচার ইঞ্জিন"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(low_hz, high_hz, SAMPLE_RATE, order=2)
    filtered = lfilter(b, a, noise)

    # প্রাকৃতিক ওঠানামা (Wave / Wind modulation)
    mod = 0.65 + 0.35 * np.sin(2 * np.pi * mod_freq * t + np.random.uniform(0, 6.28))
    out = filtered * mod

    # ফোঁটা বা স্ফুলিঙ্গ (Raindrops / Fire sparks / Debris)
    if crackle_rate > 0:
        sparks = (np.random.rand(n) > (1.0 - crackle_rate)).astype(np.float32) * np.random.normal(0, 3.0, n)
        b_hi, a_hi = butter_bandpass(1500, 6000, SAMPLE_RATE, order=2)
        out += lfilter(b_hi, a_hi, sparks)

    return normalize_and_fade(out, volume=volume, fade_in=0.15, fade_out=0.2)


def engine_resonance(freqs, decay, scrape_mix=0.2, duration_sec=0.8, volume=0.5):
    """তলোয়ার, ধাতু, ঘড়ি, কাঁচ বা ম্যাজিক্যাল শিমারের রেজোন্যান্স ইঞ্জিন"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    tone = np.zeros(n)
    for idx, f in enumerate(freqs):
        tone += np.sin(2 * np.pi * f * t) * np.exp(-t * (decay + idx * 1.8))

    if scrape_mix > 0:
        scrape = np.random.normal(0, 1, n) * np.exp(-t * (decay * 4))
        b, a = butter_highpass(2000, SAMPLE_RATE, order=2)
        tone += scrape_mix * lfilter(b, a, scrape)

    return normalize_and_fade(tone, volume=volume, fade_in=0.005, fade_out=0.08)


def engine_motion(f_low, f_high, duration_sec=0.35, speed_curve=1.0, volume=0.3):
    """গাড়ি, তীর, ক্যামেরা জুম বা ট্রানজিশন গতির ইঞ্জিন"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)
    b, a = butter_bandpass(f_low, f_high, SAMPLE_RATE, order=2)
    filtered = lfilter(b, a, noise)
    env = (np.sin(np.pi * (t / duration_sec)) ** speed_curve)
    return normalize_and_fade(filtered * env, volume=volume, fade_in=0.02, fade_out=0.05)


# ==============================================================================
# ৩. ডাইনামিক ফোলি লাইব্রেরি (প্যারামেট্রিক ইঞ্জিন দিয়ে অন-দ্য-ফ্লাই তৈরি)
# ==============================================================================
def generate_dynamic_sfx(action_type, dur=1.0):
    if action_type == "thunder":
        rumble = engine_impact(95, 24, decay=1.1, noise_mix=0.65, distortion=2.2, duration_sec=2.4, volume=0.75)
        return rumble
    elif action_type == "gunshot":
        return engine_impact(420, 35, decay=14.0, noise_mix=0.75, distortion=3.5, duration_sec=0.55, volume=0.78)
    elif action_type == "boom":
        return engine_impact(145, 28, decay=2.4, noise_mix=0.25, distortion=2.5, duration_sec=1.5, volume=0.75)
    elif action_type == "crumble":
        return engine_texture(90, 950, duration_sec=1.8, mod_freq=2.2, crackle_rate=0.004, volume=0.60)
    elif action_type == "dig":
        thud = engine_impact(130, 42, decay=16.0, noise_mix=0.55, distortion=1.8, duration_sec=0.35, volume=0.55)
        return thud
    elif action_type == "sword":
        return engine_resonance([1480, 2240, 3410, 4920], decay=5.5, scrape_mix=0.45, duration_sec=0.75, volume=0.52)
    elif action_type == "chime":
        return engine_resonance([587.33, 880.0, 1174.66, 1760.0], decay=3.2, scrape_mix=0.0, duration_sec=1.2, volume=0.45)
    elif action_type == "tick":
        return engine_resonance([2200, 3900], decay=80.0, scrape_mix=0.1, duration_sec=0.07, volume=0.38)
    elif action_type == "pop":
        return engine_impact(850, 260, decay=35.0, noise_mix=0.05, distortion=1.1, duration_sec=0.11, volume=0.42)
    elif action_type == "paper":
        return engine_texture(1400, 5200, duration_sec=0.65, mod_freq=9.0, crackle_rate=0.002, volume=0.40)
    elif action_type == "vehicle":
        return engine_motion(90, 480, duration_sec=min(2.5, dur), speed_curve=1.2, volume=0.42)
    else:  # subtle swoosh
        return engine_motion(280, 1050, duration_sec=0.32, speed_curve=2.0, volume=0.25)


def generate_dynamic_ambience(amb_type, dur):
    if amb_type == "rain":
        return engine_texture(800, 5500, duration_sec=dur, mod_freq=0.25, crackle_rate=0.005, volume=0.22)
    elif amb_type == "water":
        return engine_texture(220, 1400, duration_sec=dur, mod_freq=0.18, crackle_rate=0.001, volume=0.20)
    elif amb_type == "fire":
        return engine_texture(110, 850, duration_sec=dur, mod_freq=1.8, crackle_rate=0.0025, volume=0.18)
    elif amb_type == "crowd":
        return engine_texture(260, 1100, duration_sec=dur, mod_freq=0.8, crackle_rate=0.0005, volume=0.15)
    elif amb_type == "space":
        return engine_texture(60, 240, duration_sec=dur, mod_freq=0.12, crackle_rate=0.0, volume=0.16)
    else:  # natural air/wind
        return engine_texture(160, 620, duration_sec=dur, mod_freq=0.3, crackle_rate=0.0, volume=0.12)


# ==============================================================================
# ৪. মুড-ভিত্তিক ডাইনামিক মিউজিক কম্পোজার (Dynamic Mood BGM)
# ==============================================================================
def compose_dynamic_bgm(duration_sec, mood="suspense", volume=0.18):
    """ভিডিওর মুড (suspense, action, emotional, mystery) অনুযায়ী কর্ড ও বিট তৈরি করে"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    mood_profiles = {
        "action": {
            "roots": [82.41, 65.41, 73.42, 61.74],   # E2, C2, D2, B1
            "third": 1.189, "pulse_hz": 0.25, "tempo_decay": 14.0, "cutoff": 1600
        },
        "emotional": {
            "roots": [65.41, 49.00, 55.00, 43.65],   # C2, G1, A1, F1
            "third": 1.260, "pulse_hz": 1.0, "tempo_decay": 5.0, "cutoff": 900
        },
        "mystery": {
            "roots": [61.74, 65.41, 58.27, 55.00],   # B1, C2, Bb1, A1
            "third": 1.189, "pulse_hz": 0.75, "tempo_decay": 8.0, "cutoff": 1050
        },
        "suspense": {
            "roots": [73.42, 58.27, 49.00, 55.00],   # D2, Bb1, G1, A1
            "third": 1.189, "pulse_hz": 0.5, "tempo_decay": 11.0, "cutoff": 1250
        }
    }
    prof = mood_profiles.get(mood, mood_profiles["suspense"])
    roots = prof["roots"]

    bass = np.zeros(n)
    pad = np.zeros(n)
    step_samples = int(4.0 * SAMPLE_RATE)

    for idx, start in enumerate(range(0, n, step_samples)):
        end = min(n, start + step_samples)
        seg_t = t[start:end]
        f0 = roots[idx % len(roots)]
        bass[start:end] = np.sin(2 * np.pi * f0 * seg_t) + 0.25 * np.sin(2 * np.pi * (f0 * 2) * seg_t)
        pad[start:end] = (
            0.4 * np.sin(2 * np.pi * (f0 * 4) * seg_t)
            + 0.3 * np.sin(2 * np.pi * (f0 * 4 * prof["third"]) * seg_t)
            + 0.3 * np.sin(2 * np.pi * (f0 * 6) * seg_t)
        )

    p_phase = (t % prof["pulse_hz"]) / prof["pulse_hz"]
    rhythm = np.exp(-p_phase * prof["tempo_decay"]) * np.sin(2 * np.pi * 62.0 * t)

    hat_noise = np.random.normal(0, 1, n)
    b_hi, a_hi = butter_highpass(5200, SAMPLE_RATE, order=2)
    hat_noise = lfilter(b_hi, a_hi, hat_noise)
    hat_env = np.exp(-((t % 0.25) / 0.25) * 28.0) * (0.28 if mood == "action" else 0.16)
    hats = hat_noise * hat_env

    raw_bgm = 0.55 * bass + 0.35 * pad + 0.45 * rhythm + 0.20 * hats
    b_lp, a_lp = butter_lowpass(prof["cutoff"], SAMPLE_RATE, order=2)
    smooth_bgm = lfilter(b_lp, a_lp, raw_bgm)

    return normalize_and_fade(smooth_bgm, volume=volume, fade_in=0.6, fade_out=0.8)


# ==============================================================================
# ৫. ভিজ্যুয়াল, কালার, মোশন ও স্ক্রিপ্ট বিশ্লেষক (Universal Context Analyzer)
# ==============================================================================
def analyze_clip_context(html_path, chunk_idx, total_dur_sec):
    events = []
    ambiences = []
    html_code = ""
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

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

    full_context = (html_code + " " + narration_text).lower()

    # পুরো ক্লিপের মিউজিক মুড নির্ধারণ
    if re.search(r"(war|battle|attack|gun|shoot|chase|fast|explode|danger|fight)", full_context):
        mood = "action"
    elif re.search(r"(sad|cry|death|pray|holy|hope|love|tear|peace|god)", full_context):
        mood = "emotional"
    elif re.search(r"(secret|mystery|hidden|ancient|unknown|clue|puzzle|space|alien)", full_context):
        mood = "mystery"
    else:
        mood = "suspense"

    # শটগুলোর টাইমলাইন বের করা
    shot_cuts = [0.0]
    for m in re.finditer(r"t_ms\s*<\s*(\d+)", html_code):
        sec = int(m.group(1)) / 1000.0
        if 0.8 < sec < total_dur_sec - 0.5:
            shot_cuts.append(sec)
    shot_cuts = sorted(list(set(shot_cuts)))
    shot_cuts.append(total_dur_sec)

    shot_blocks = re.split(r"if\s*\(\s*activeShot\s*===\s*\d+\s*\)", html_code)

    for idx in range(len(shot_cuts) - 1):
        s_start = shot_cuts[idx]
        s_end = shot_cuts[idx + 1]
        s_dur = max(0.5, s_end - s_start)
        block = (shot_blocks[idx + 1] if (idx + 1) < len(shot_blocks) else html_code).lower()

        if idx > 0 and s_dur >= 2.2:
            events.append((max(0.0, s_start - 0.12), "swoosh", 0.35))

        # ফিজিক্স ও অ্যাকশন ডিটেকশন (টেক্সট + ভিজ্যুয়াল প্যাটার্ন)
        if re.search(r"(thunder|lightning|storm|flash)", block):
            events.append((s_start + 0.1, "thunder", 2.4))
        elif re.search(r"(gun|shoot|bullet|rifle|pistol|sniper)", block):
            for t_g in np.arange(s_start + 0.2, min(s_end - 0.2, s_start + 2.5), 0.45):
                events.append((float(t_g), "gunshot", 0.55))
        elif re.search(r"(crumble|destroy|temple|ruin|collapse|fall|earthquake|blast|explode)", block):
            events.append((s_start + 0.12, "boom", 1.5))
            events.append((s_start + 0.30, "crumble", 1.8))
        elif re.search(r"(dig|shovel|pickaxe|earth|excavat|bury|hill|dirt)", block):
            for t_d in np.arange(s_start + 0.3, s_end - 0.3, 0.85):
                events.append((float(t_d), "dig", 0.35))
        elif re.search(r"(war|sword|army|battle|soldier|emperor|roman|shield|knife)", block):
            events.append((s_start + 0.2, "sword", 0.75))
            events.append((s_start + 0.25, "boom", 1.5))
        elif re.search(r"(car|train|plane|rocket|engine|drive|speed|ship)", block):
            events.append((s_start + 0.15, "vehicle", s_dur))
        elif re.search(r"(map|pin|route|path|scroll|jerusalem|location|arrow|book|page)", block):
            events.append((s_start + 0.15, "paper", 0.65))
            events.append((s_start + s_dur * 0.45, "pop", 0.12))
        elif re.search(r"(clock|dial|century|centuries|year|time|timer)", block):
            for t_tk in np.arange(s_start + 0.25, s_end - 0.25, 0.5):
                events.append((float(t_tk), "tick", 0.07))
        elif re.search(r"(discover|treasure|gold|church|holy|cross|tomb|light|glow|star)", block):
            events.append((s_start + 0.25, "chime", 1.2))
        else:
            events.append((s_start + 0.15, "pop", 0.12))

        # অ্যাম্বিয়েন্স লেয়ার (রঙ ও পরিবেশ বিশ্লেষণসহ)
        if re.search(r"(rain|storm|drop|wet|monsoon)", block):
            ambiences.append((s_start, s_end, "rain"))
        elif re.search(r"(ocean|sea|river|water|wave|underwater|boat)", block):
            ambiences.append((s_start, s_end, "water"))
        elif re.search(r"(fire|torch|flame|burn|#ff4|#f97316|#ef4444)", block):
            ambiences.append((s_start, s_end, "fire"))
        elif re.search(r"(crowd|city|market|people|street|village|kingdom)", block):
            ambiences.append((s_start, s_end, "crowd"))
        elif re.search(r"(space|galaxy|planet|cosmos|orbit|void)", block):
            ambiences.append((s_start, s_end, "space"))
        else:
            ambiences.append((s_start, s_end, "wind"))

    return events, ambiences, mood


# ==============================================================================
# ৬. মাল্টি-লেয়ার অডিও মিক্সার
# ==============================================================================
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

    events, ambiences, mood = analyze_clip_context(html_path, chunk_idx, total_dur)

    # ১. মুড-ভিত্তিক ডাইনামিক BGM + অটো-ডাকিং
    bgm = compose_dynamic_bgm(total_dur, mood=mood, volume=0.18)
    voice_env = np.convolve(np.abs(voice), np.ones(int(SAMPLE_RATE * 0.25)) / (SAMPLE_RATE * 0.25), mode='same')
    ducking = np.where(voice_env > 0.015, 0.58, 1.0)
    bgm = bgm * ducking

    # ২. ডাইনামিক অ্যাম্বিয়েন্স ট্র্যাক
    ambience_track = np.zeros_like(voice)
    for a_start, a_end, a_type in ambiences:
        seg_dur = max(0.2, a_end - a_start)
        mix_segment(ambience_track, generate_dynamic_ambience(a_type, seg_dur), a_start)

    # ৩. প্যারামেট্রিক ফোলি ও SFX ট্র্যাক
    sfx_track = np.zeros_like(voice)
    for t_sec, sfx_name, dur in events:
        mix_segment(sfx_track, generate_dynamic_sfx(sfx_name, dur), t_sec)

    # ফাইনাল মাস্টারিং
    mixed = (voice * 1.0) + (sfx_track * 0.85) + (ambience_track * 0.80) + bgm
    mixed = np.tanh(mixed * 0.95)

    final_int16 = np.int16(np.clip(mixed, -1.0, 1.0) * 32767)
    wavfile.write(output_wav_path, SAMPLE_RATE, final_int16)
    print(f"Generated universal dynamic audio [{mood}]: {output_wav_path} ({len(events)} SFX cues, {len(ambiences)} ambiences)", flush=True)
