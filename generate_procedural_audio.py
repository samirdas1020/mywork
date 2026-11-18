import os
import re
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SAMPLE_RATE = 44100


# ==============================================================================
# ১. অডিও ফিল্টার ও প্রসিডিউরাল সাউন্ড সিন্থেসাইজার (SFX + BGM)
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


def synth_whoosh(duration_sec=0.45, volume=0.65):
    """ট্রানজিশন বা শট পরিবর্তনের আধুনিক বাতাসের সাউন্ড (Swoosh/Whoosh)"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    noise = np.random.normal(0, 1, n)

    # ফ্রেম বাই ফ্রেম ফ্রিকোয়েন্সি সুইপ (250Hz -> 2400Hz -> 400Hz)
    chunk_size = 512
    out = np.zeros(n)
    for i in range(0, n, chunk_size):
        progress = i / n
        center_freq = 250 + 2200 * np.sin(np.pi * progress)
        b, a = butter_bandpass(center_freq * 0.6, center_freq * 1.4, SAMPLE_RATE, order=2)
        seg = lfilter(b, a, noise[i:i + chunk_size])
        out[i:i + len(seg)] = seg

    env = np.sin(np.pi * (t / duration_sec)) ** 1.5
    out = out / (np.max(np.abs(out)) + 1e-6)
    return out * env * volume


def synth_pop(duration_sec=0.14, volume=0.60):
    """টেক্সট বা আইকন পপ-আপ হওয়ার ক্লিন সাউন্ড (Pop / Blip)"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    # 950Hz থেকে দ্রুত 260Hz-এ নামা Sine wave
    freq = 260 + 690 * np.exp(-t * 38)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    wave = np.sin(phase)
    env = np.exp(-t * 26) * (1 - np.exp(-t * 400))
    return wave * env * volume


def synth_boom(duration_sec=1.3, volume=0.85):
    """নাটকীয় মুহূর্ত বা ধ্বংসের গভীর বেস সাউন্ড (Cinematic Impact Boom)"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    # Sub-bass 140Hz থেকে 32Hz
    freq = 32 + 108 * np.exp(-t * 7.5)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase) + 0.35 * np.tanh(2.5 * np.sin(phase))

    # শুরুতে হালকা ক্রাঞ্চ/ইমপ্যাক্ট নয়েজ
    impact_noise = np.random.normal(0, 1, n) * np.exp(-t * 22)
    b, a = butter_lowpass(900, SAMPLE_RATE, order=2)
    impact_noise = lfilter(b, a, impact_noise)

    env = np.exp(-t * 2.8) * (1 - np.exp(-t * 300))
    out = (sub + 0.4 * impact_noise) * env
    out = out / (np.max(np.abs(out)) + 1e-6)
    return out * volume


def synth_tick(duration_sec=0.07, volume=0.45):
    """সময় বয়ে যাওয়া বা ঘড়ির টিক-টিক সাউন্ড"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    click = np.sin(2 * np.pi * 1800 * t) + 0.5 * np.sin(2 * np.pi * 3200 * t)
    env = np.exp(-t * 75)
    return click * env * volume


def synth_riser(duration_sec=1.5, volume=0.50):
    """ক্লাইম্যাক্সের আগে টেনশন বিল্ড-আপ (Riser)"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    prog = t / duration_sec
    freq = 110 * (4 ** prog)  # 110Hz -> 440Hz
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    wave = 0.6 * np.sin(phase) + 0.4 * (2 * (phase / (2 * np.pi) % 1) - 1)
    b, a = butter_lowpass(1600, SAMPLE_RATE, order=2)
    wave = lfilter(b, a, wave)
    env = (prog ** 2.2) * np.exp(-np.maximum(0, prog - 0.92) * 30)
    return wave * env * volume


def synth_suspense_bgm(duration_sec, volume=0.14):
    """পুরো ক্লিপের জন্য ডকুমেন্টারি/সাসপেন্স ব্যাকগ্রাউন্ড মিউজিক (BGM)"""
    n = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    # D Minor ডার্ক অ্যাম্বিয়েন্ট ড্রোন (D2 = 73.42Hz, A2 = 110Hz, F3 = 174.61Hz)
    drone = (
        0.55 * np.sin(2 * np.pi * 73.42 * t + 0.4 * np.sin(2 * np.pi * 0.25 * t))
        + 0.30 * np.sin(2 * np.pi * 110.0 * t + 0.3 * np.sin(2 * np.pi * 0.18 * t))
        + 0.15 * np.sin(2 * np.pi * 174.61 * t)
    )

    # ডকুমেন্টারি হার্টবিট পালস (প্রতি ১.২ সেকেন্ডে একবার লো পালস)
    beat_period = 1.2
    beat_phase = (t % beat_period) / beat_period
    pulse = np.exp(-beat_phase * 9.0) * np.sin(2 * np.pi * 55.0 * t)

    # প্রথম ২.৫ সেকেন্ড (Hook) ও শেষ ৩ সেকেন্ডে হালকা ইনটেনসিটি বুস্ট
    dynamic_curve = np.ones(n)
    hook_n = min(n, int(2.5 * SAMPLE_RATE))
    dynamic_curve[:hook_n] = np.linspace(1.25, 1.0, hook_n)

    raw_bgm = (0.75 * drone + 0.45 * pulse) * dynamic_curve
    b, a = butter_lowpass(420, SAMPLE_RATE, order=2)
    smooth_bgm = lfilter(b, a, raw_bgm)

    # শুরুতে ও শেষে স্মুথ ফেড-ইন/ফেড-আউট
    fade_n = min(n // 4, int(0.8 * SAMPLE_RATE))
    smooth_bgm[:fade_n] *= np.linspace(0, 1, fade_n)
    smooth_bgm[-fade_n:] *= np.linspace(1, 0, fade_n)

    smooth_bgm = smooth_bgm / (np.max(np.abs(smooth_bgm)) + 1e-6)
    return smooth_bgm * volume


# ==============================================================================
# ২. স্মার্ট HTML কোড স্ক্যানার (কোনো প্রম্পট পরিবর্তন ছাড়াই অ্যাকশন শনাক্তকরণ)
# ==============================================================================
def detect_audio_events_from_html(html_path, total_dur_sec):
    """HTML ফাইলের JS অ্যানিমেশন লজিক পড়ে সাউন্ড ইফেক্টের টাইমস্ট্যাম্প বের করে"""
    events = []  # (time_sec, sfx_type)
    if not os.path.exists(html_path):
        return events

    with open(html_path, "r", encoding="utf-8") as f:
        code = f.read()

    # ১. শট পরিবর্তন (t_ms < 4000, t_ms < 10100 ইত্যাদি) -> Whoosh + Pop
    shot_cuts = [0.0]
    for m in re.finditer(r"t_ms\s*<\s*(\d+)", code):
        cut_sec = int(m.group(1)) / 1000.0
        if 0.5 < cut_sec < total_dur_sec - 0.3:
            shot_cuts.append(cut_sec)

    shot_cuts = sorted(list(set(shot_cuts)))
    for idx, t_sec in enumerate(shot_cuts):
        if idx > 0:
            # শট পরিবর্তনের ঠিক আগে Whoosh এবং পরপরই টাইটেল Pop
            events.append((max(0.0, t_sec - 0.15), "whoosh"))
            events.append((t_sec + 0.12, "pop"))
        else:
            events.append((0.1, "pop"))

    # শট ব্লক অনুযায়ী ভেতরের অ্যাকশন বিশ্লেষণ
    shot_blocks = re.split(r"if\s*\(\s*activeShot\s*===\s*\d+\s*\)", code)
    for b_idx, block in enumerate(shot_blocks[1:]):
        start_t = shot_cuts[b_idx] if b_idx < len(shot_cuts) else 0.0
        end_t = shot_cuts[b_idx + 1] if (b_idx + 1) < len(shot_cuts) else total_dur_sec
        dur = max(1.0, end_t - start_t)

        # ২. ধ্বংস, কম্পন বা ধাক্কা (shake, crumble, slam, blast) -> Cinematic Boom
        if re.search(r"(shake|crumble|slam|blast|impact|dust)", block, re.IGNORECASE):
            events.append((start_t + dur * 0.25, "boom"))

        # ৩. ঘড়ি বা সময় গণনা (clock, dial, year) -> Ticking Clock
        if re.search(r"(clock|dial|year-counter|handRot)", block, re.IGNORECASE):
            for tick_t in np.arange(start_t + 0.3, end_t - 0.4, 0.55):
                events.append((float(tick_t), "tick"))

        # ৪. পিন, অ্যারো বা রিভিল অ্যানিমেশন -> Pop
        if re.search(r"(pin|arrow|reveal|markP|digP)", block, re.IGNORECASE):
            events.append((start_t + dur * 0.45, "pop"))

    # ৫. ক্লিপের একদম শেষে ক্লাইম্যাক্স Riser
    if total_dur_sec > 4.0:
        events.append((total_dur_sec - 1.5, "riser"))

    return events


# ==============================================================================
# ৩. অডিও মিক্সিং ও এক্সপোর্ট (Voiceover + SFX + BGM)
# ==============================================================================
def place_sfx(track, sfx_wave, start_sec):
    start_idx = int(start_sec * SAMPLE_RATE)
    if start_idx >= len(track):
        return
    end_idx = min(len(track), start_idx + len(sfx_wave))
    track[start_idx:end_idx] += sfx_wave[:end_idx - start_idx]


def build_clip_audio(html_path, voice_mp3_path, output_wav_path):
    # ভয়েসওভার WAV-এ রূপান্তর করে লোড করা
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

    # ১. BGM তৈরি ও অটো-ডাকিং (ভয়েস চললে BGM হালকা কমে যাবে)
    bgm = synth_suspense_bgm(total_dur, volume=0.16)
    voice_envelope = np.convolve(np.abs(voice), np.ones(int(SAMPLE_RATE * 0.3)) / (SAMPLE_RATE * 0.3), mode='same')
    ducking_gain = np.where(voice_envelope > 0.015, 0.65, 1.0)
    bgm = bgm * ducking_gain

    # ২. HTML অ্যানালাইজ করে SFX ট্র্যাক তৈরি
    sfx_track = np.zeros_like(voice)
    events = detect_audio_events_from_html(html_path, total_dur)

    sfx_bank = {
        "whoosh": synth_whoosh(),
        "pop": synth_pop(),
        "boom": synth_boom(),
        "tick": synth_tick(),
        "riser": synth_riser(),
    }

    for t_sec, sfx_type in events:
        if sfx_type in sfx_bank:
            place_sfx(sfx_track, sfx_bank[sfx_type], t_sec)

    # ৩. সব ট্র্যাক একসাথে মিক্স ও লিমিটার (যাতে সাউন্ড ফেটে না যায়)
    mixed = voice * 1.0 + sfx_track * 0.85 + bgm
    mixed = np.tanh(mixed * 0.95)  # Soft limiter

    final_int16 = np.int16(np.clip(mixed, -1.0, 1.0) * 32767)
    wavfile.write(output_wav_path, SAMPLE_RATE, final_int16)
    print(f"Generated procedural audio: {output_wav_path} ({len(events)} SFX cues synced)", flush=True)


if __name__ == "__main__":
    # উদাহরণ ব্যবহার:
    # build_clip_audio("render_input/scene_1.html", "prompts_output/audio_1.mp3", "clips/final_audio_1.wav")
    pass
