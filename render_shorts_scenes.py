import array
import glob
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import wave

try:
  import numpy as np

  HAS_NUMPY = True
except ImportError:
  np = None
  HAS_NUMPY = False

FPS = 30
WIDTH, HEIGHT = 720, 1280
SCALE = 1.5  # Renders 720x1280 canvas directly as 1080x1920 (Full HD Vertical)
IN_DIR = "render_input"  # scene_N.html, audio_N.mp3, chunks.json
OUT_DIR = "clips"

# Deep Scene Kinematics & Visual Action Inspector (Runs every frame at 30 FPS)
STEP_JS = """t => {
  document.getAnimations().forEach(a => {
    try { a.pause(); a.currentTime = t; } catch (e) {}
  });
  document.querySelectorAll('svg').forEach(s => {
    try { s.pauseAnimations(); s.setCurrentTime(t / 1000); } catch (e) {}
  });
  if (window.updateSceneTime) window.updateSceneTime(t);

  const isVisible = (el) => {
    let cur = el;
    while (cur && cur !== document.body) {
      const st = window.getComputedStyle(cur);
      if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') <= 0.08) {
        return false;
      }
      cur = cur.parentElement;
    }
    return true;
  };

  let activeShots = [];
  let visibleTexts = [];
  let camX = 0, camY = 0, camScale = 1, camCount = 0;
  let limbAngles = 0;
  let legMotion = 0;
  let mapProgress = 0;
  let hasFire = false;
  let hasCrownOrGold = false;
  let visibleCount = 0;

  // 1. Detect Active Shots (works with id="shot-N", id="scene-N", or top-level <g>)
  const shotCandidates = document.querySelectorAll('[id^="shot"], [id*="scene"], svg > g');
  shotCandidates.forEach((el, idx) => {
    if (!isVisible(el)) return;
    const tagId = el.id || ('top_g_' + idx);
    if (el.id && (el.id.startsWith('shot') || el.id.includes('scene'))) {
      activeShots.push(tagId);
    } else if (el.parentElement && el.parentElement.tagName.toLowerCase() === 'svg') {
      activeShots.push(tagId);
    }
    try {
      const ctm = el.getCTM && el.getCTM();
      if (ctm && isFinite(ctm.a) && isFinite(ctm.b) && isFinite(ctm.e) && isFinite(ctm.f)) {
        camX += ctm.e;
        camY += ctm.f;
        camScale += Math.hypot(ctm.a, ctm.b);
        camCount++;
      }
    } catch (e) {}
  });

  if (camCount > 0) {
    camX /= camCount;
    camY /= camCount;
    camScale /= camCount;
  }

  // 2. Detect Visible Texts / Titles / Dates / Numbers
  document.querySelectorAll('text, [id*="title"], [id*="label"], [class*="title"]').forEach(el => {
    const txt = (el.textContent || '').trim();
    if (txt.length > 0 && isVisible(el)) {
      visibleTexts.push(txt.slice(0, 24));
    }
  });

  // 3. Scan All Visual Elements Inside the Active Scene for Micro-Actions
  document.querySelectorAll('g, path, line, circle, rect, polygon').forEach(el => {
    if (!isVisible(el)) return;
    visibleCount++;
    const tag = ((el.id || '') + ' ' + (el.getAttribute('class') || '')).toLowerCase();
    const tr = el.getAttribute('transform') || '';

    if (/(sword|weapon|arm|hand|spear|axe|bow|arrow|blade|shield|hit|slash)/.test(tag)) {
      const m = tr.match(/rotate\(([-\d.]+)/);
      if (m) limbAngles += Math.abs(parseFloat(m[1]));
    } else if (tr.includes('rotate')) {
      const m = tr.match(/rotate\(([-\d.]+)/);
      if (m) limbAngles += Math.abs(parseFloat(m[1])) * 0.25;
    }

    if (/(leg|foot|march|soldier|troop|army|horse|walk)/.test(tag)) {
      const m = tr.match(/(?:rotate|translate)\(([-\d.]+)/);
      if (m) legMotion += Math.abs(parseFloat(m[1]));
    }

    const dash = el.getAttribute('stroke-dashoffset') || window.getComputedStyle(el).strokeDashoffset;
    if (dash && dash !== 'none' && dash !== '0px') {
      const val = parseFloat(dash);
      if (!isNaN(val)) mapProgress += Math.abs(val);
    }
    if (/(arrow|route|border|map|front|line)/.test(tag) && tr) {
      mapProgress += tr.length * 2;
    }

    if (/(fire|flame|torch|smoke|ember|explosion|blast|cannon)/.test(tag)) {
      hasFire = true;
    }

    if (/(crown|gold|king|throne|treasure|coin|star|medal|royal)/.test(tag)) {
      hasCrownOrGold = true;
    }
  });

  return {
    shots: activeShots.join('|'),
    texts: visibleTexts.join('|'),
    camX: Math.round(camX * 10) / 10,
    camY: Math.round(camY * 10) / 10,
    camScale: Math.round(camScale * 1000) / 1000,
    limbAngles: Math.round(limbAngles * 10) / 10,
    legMotion: Math.round(legMotion * 10) / 10,
    mapProgress: Math.round(mapProgress),
    hasFire: hasFire,
    hasCrownOrGold: hasCrownOrGold,
    visibleCount: visibleCount
  };
}"""

INIT_JS = """
window.requestAnimationFrame = () => 0;
window.setInterval = () => 0;
window.setTimeout = () => 0;
"""

MIN_GAP_MS = {
    "boom": 650,
    "bass_drop": 1200,
    "horn": 1800,
    "cannon": 900,
    "whoosh": 360,
    "swoosh": 300,
    "sword": 320,
    "pop": 220,
    "typewriter": 420,
    "clock": 1400,
    "shimmer": 1000,
    "map": 420,
    "march": 360,
    "fire": 1000,
    "riser": 1100,
}


def extract_timeline_cues(chunk_meta):
  """Analyzes chunks.json English timeline & narration keywords for viral YouTube Shorts SFX."""
  cues = []
  timeline = chunk_meta.get("timeline", "")

  battle_kw = (
      r"\b(war|wars|battle|battles|sword|swords|attack|attacked|attacks|army|armies|"
      r"fight|fighting|fought|strike|struck|blood|kill|killed|soldier|soldiers|"
      r"warrior|warriors|combat|clash|spear|spears|shield|shields|blade|ambush)\b"
  )
  cannon_kw = (
      r"\b(cannon|cannons|gun|guns|bomb|bombs|explode|exploded|explosion|fire|fired|"
      r"artillery|blast|destroy|destroyed|siege|musket|muskets|gunpowder|shatter)\b"
  )
  impact_kw = (
      r"\b(empire|empires|fall|fell|fallen|death|dead|power|shock|shocked|betray|"
      r"betrayed|betrayal|defeat|defeated|collapse|collapsed|murder|murdered|doom|"
      r"disaster|crush|crushed|execute|executed|assassinate|assassinated)\b"
  )
  horn_kw = (
      r"\b(invasion|massive|thousand|thousands|million|millions|conquer|conquered|"
      r"conquest|world|history|emperor|kingdom|kingdoms|legion|legions|dynasty|reign)\b"
  )
  clock_kw = (
      r"\b(time|year|years|century|centuries|wait|waited|hour|hours|night|secret|"
      r"secrets|plan|planned|mystery|suddenly|countdown|deadline|trap|trapped)\b"
  )
  shimmer_kw = (
      r"\b(gold|golden|treasure|rich|riches|crown|crowned|king|kings|queen|queens|"
      r"throne|wealth|miracle|victory|victorious|glory|royal|diamond|fortune)\b"
  )
  march_kw = (
      r"\b(march|marched|marching|advance|advanced|invade|invaded|cross|crossed|"
      r"journey|troops|border|borders|cavalry|fleet|forged)\b"
  )

  for line in timeline.splitlines():
    m = re.match(r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(.*)", line)
    if not m:
      continue
    start_s = float(m.group(1))
    end_s = float(m.group(2))
    content = m.group(3)
    start_ms = int(start_s * 1000)
    dur_s = end_s - start_s

    if "VisualSetup" in content.replace(" ", "") or "Visual Setup" in content:
      cues.append({"time_ms": start_ms, "type": "bass_drop", "intensity": 0.85})
    elif "Visual Hold" in content and start_ms > 1000:
      cues.append(
          {"time_ms": max(0, start_ms - 850), "type": "riser", "intensity": 0.75}
      )
      cues.append({"time_ms": start_ms, "type": "bass_drop", "intensity": 0.80})
    elif "Narration & Action:" in content:
      if re.search(cannon_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 180, "type": "cannon", "intensity": 0.92})
      elif re.search(battle_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 220, "type": "sword", "intensity": 0.86})

      if re.search(horn_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 100, "type": "horn", "intensity": 0.82})
      elif re.search(impact_kw, content, re.IGNORECASE):
        cues.append(
            {"time_ms": start_ms + 140, "type": "bass_drop", "intensity": 0.82}
        )

      if re.search(clock_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 180, "type": "clock", "intensity": 0.76})

      if re.search(shimmer_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 260, "type": "shimmer", "intensity": 0.78})

      if re.search(march_kw, content, re.IGNORECASE):
        cues.append({"time_ms": start_ms + 300, "type": "march", "intensity": 0.72})

      if re.search(r"\b\d{3,4}\b", content):
        cues.append(
            {"time_ms": start_ms + 140, "type": "typewriter", "intensity": 0.72}
        )

      if dur_s >= 5.0:
        cues.append({
            "time_ms": int((end_s - 0.95) * 1000),
            "type": "riser",
            "intensity": 0.70,
        })

  return cues


def _dedupe_cues(cues):
  ordered = sorted(cues, key=lambda x: x.get("time_ms", 0))
  filtered = []
  last_by_type = {}
  for c in ordered:
    ct = str(c.get("type", "whoosh")).lower()
    tms = int(c.get("time_ms", 0))
    if tms - last_by_type.get(ct, -99999) < MIN_GAP_MS.get(ct, 300):
      continue
    last_by_type[ct] = tms
    filtered.append({
        "time_ms": tms,
        "type": ct,
        "intensity": min(max(float(c.get("intensity", 0.8)), 0.2), 1.2),
    })
  return filtered


def _write_wav_from_floats(samples, sr, out_wav):
  total = len(samples)
  fade_in = min(int(0.015 * sr), total // 4)
  fade_out = min(int(0.040 * sr), total // 4)

  if HAS_NUMPY:
    arr = np.asarray(samples, dtype=np.float64)
    if total > 0:
      gains = np.ones(total, dtype=np.float64)
      if fade_in > 0:
        gains[:fade_in] = np.linspace(0.0, 1.0, fade_in, endpoint=False)
      if fade_out > 0:
        gains[-fade_out:] = np.linspace(1.0, 0.0, fade_out, endpoint=False)
      limited = np.tanh(arr * gains) * 0.92
      pcm_bytes = np.clip(limited * 32767.0, -32767.0, 32767.0).astype(
          np.int16
      ).tobytes()
  else:
    pcm = array.array("h")
    for idx, x in enumerate(samples):
      gain = 1.0
      if idx < fade_in and fade_in > 0:
        gain = idx / fade_in
      elif idx >= total - fade_out and fade_out > 0:
        gain = (total - 1 - idx) / fade_out
      limited = math.tanh(x * gain) * 0.92
      pcm.append(int(max(-32767, min(32767, limited * 32767))))
    pcm_bytes = pcm.tobytes()

  with wave.open(out_wav, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm_bytes)


def generate_bgm_wav(duration, out_wav, sr=44100):
  total_samples = max(1, int(duration * sr))
  bpm = 116.0
  beat_sec = 60.0 / bpm
  bar_sec = beat_sec * 4.0
  eighth_sec = beat_sec * 0.5

  chords = [
      (73.42, 146.83, 174.61, 220.00),  # D Minor
      (58.27, 116.54, 146.83, 174.61),  # Bb Major
      (49.00, 98.00, 116.54, 146.83),   # G Minor
      (55.00, 110.00, 138.59, 164.81),  # A Major
  ]

  if HAS_NUMPY:
    rng = np.random.default_rng(2026)
    t = np.arange(total_samples, dtype=np.float64) / sr
    chord_idx = (np.floor(t / bar_sec).astype(np.int64)) % 4

    bass_f = np.array([chords[c][0] for c in chord_idx], dtype=np.float64)
    r_f = np.array([chords[c][1] for c in chord_idx], dtype=np.float64)
    th_f = np.array([chords[c][2] for c in chord_idx], dtype=np.float64)
    fi_f = np.array([chords[c][3] for c in chord_idx], dtype=np.float64)

    bar_pos = np.mod(t, bar_sec) / bar_sec
    chord_env = np.sin(np.pi * bar_pos) ** 0.35

    lfo = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.25 * t)
    pad = (
        0.38 * np.sin(2.0 * np.pi * bass_f * t)
        + 0.20 * np.sin(2.0 * np.pi * (bass_f * 2.0) * t)
        + 0.20 * np.sin(2.0 * np.pi * r_f * t)
        + 0.14 * lfo * np.sin(2.0 * np.pi * th_f * t)
        + 0.12 * (1.0 - lfo) * np.sin(2.0 * np.pi * fi_f * t)
    ) * chord_env

    arp_step = (np.floor(t / eighth_sec).astype(np.int64)) % 4
    arp_t = np.mod(t, eighth_sec)
    arp_pos = arp_t / eighth_sec
    arp_attack = 1.0 - np.exp(-180.0 * arp_pos)
    arp_env = arp_attack * np.exp(-8.5 * arp_pos)

    c0 = chord_idx == 0
    c1 = chord_idx == 1
    c2 = chord_idx == 2
    c3 = chord_idx == 3

    arp_f = np.zeros(total_samples, dtype=np.float64)
    for mask, ch in ((c0, chords[0]), (c1, chords[1]), (c2, chords[2]), (c3, chords[3])):
      notes = [ch[1] * 2.0, ch[2] * 2.0, ch[3] * 2.0, ch[2] * 2.0]
      for s_i, nf in enumerate(notes):
        arp_f[mask & (arp_step == s_i)] = nf

    arp = 0.15 * arp_env * np.sin(2.0 * np.pi * arp_f * arp_t)

    beat_t = np.mod(t, beat_sec)
    beat_pos = beat_t / beat_sec
    kick_env = np.exp(-8.5 * beat_pos)
    kick_phase = 2.0 * np.pi * (48.0 * beat_t + 1.8 * (1.0 - np.exp(-25.0 * beat_t)))
    kick = 0.55 * kick_env * np.tanh(1.8 * np.sin(kick_phase))

    half_pos = np.mod(t + beat_sec * 0.5, beat_sec) / beat_sec
    hat_env = np.exp(-42.0 * half_pos)
    hat = 0.11 * hat_env * (rng.random(total_samples) * 2.0 - 1.0)

    buf = 0.18 * (pad + arp + kick + hat)
    _write_wav_from_floats(buf, sr, out_wav)
    return

  rng = random.Random(2026)
  buf = [0.0] * total_samples
  for idx in range(total_samples):
    t = idx / sr
    chord_idx = int(t / bar_sec) % 4
    bass_f, r_f, th_f, fi_f = chords[chord_idx]
    bar_pos = (t % bar_sec) / bar_sec
    chord_env = math.sin(math.pi * bar_pos) ** 0.35

    lfo = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.25 * t)
    pad = (
        0.38 * math.sin(2.0 * math.pi * bass_f * t)
        + 0.20 * math.sin(2.0 * math.pi * (bass_f * 2.0) * t)
        + 0.20 * math.sin(2.0 * math.pi * r_f * t)
        + 0.14 * lfo * math.sin(2.0 * math.pi * th_f * t)
        + 0.12 * (1.0 - lfo) * math.sin(2.0 * math.pi * fi_f * t)
    ) * chord_env

    arp_notes = [r_f * 2.0, th_f * 2.0, fi_f * 2.0, th_f * 2.0]
    arp_step = int(t / eighth_sec) % 4
    arp_t = t % eighth_sec
    arp_pos = arp_t / eighth_sec
    arp_env = (1.0 - math.exp(-180.0 * arp_pos)) * math.exp(-8.5 * arp_pos)
    arp = 0.15 * arp_env * math.sin(2.0 * math.pi * arp_notes[arp_step] * arp_t)

    beat_t = t % beat_sec
    beat_pos = beat_t / beat_sec
    kick_env = math.exp(-8.5 * beat_pos)
    kick_phase = 2.0 * math.pi * (48.0 * beat_t + 1.8 * (1.0 - math.exp(-25.0 * beat_t)))
    kick = 0.55 * kick_env * math.tanh(1.8 * math.sin(kick_phase))

    half_pos = ((t + beat_sec * 0.5) % beat_sec) / beat_sec
    hat_env = math.exp(-42.0 * half_pos)
    hat = 0.11 * hat_env * (rng.random() * 2.0 - 1.0)

    buf[idx] = 0.18 * (pad + arp + kick + hat)

  _write_wav_from_floats(buf, sr, out_wav)


def generate_sfx_wav(duration, cues, out_wav, seed=0, sr=44100):
  """Dedicated 14-SFX track so impact cues have clean punch separate from BGM."""
  total_samples = max(1, int(duration * sr))
  buf = [0.0] * total_samples
  rng = random.Random(2026 + seed)
  filtered_cues = _dedupe_cues(cues)

  def add_sample(idx, val):
    if 0 <= idx < total_samples:
      buf[idx] += val

  for cue in filtered_cues:
    t0 = float(cue["time_ms"]) / 1000.0
    ctype = cue["type"]
    intensity = cue["intensity"]
    start_idx = int(t0 * sr)

    if ctype == "boom":
      dur = 1.0
      n = int(dur * sr)
      phase = 0.0
      lp = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-4.5 * u)
        freq = 38.0 + 90.0 * math.exp(-16.0 * u)
        phase += 2.0 * math.pi * freq / sr
        noise = rng.random() * 2.0 - 1.0
        lp = 0.88 * lp + 0.12 * noise
        val = (0.80 * math.tanh(1.6 * math.sin(phase)) + 0.35 * lp * math.exp(-14.0 * u)) * env
        add_sample(start_idx + k, val * 0.82 * intensity)

    elif ctype == "bass_drop":
      dur = 1.25
      n = int(dur * sr)
      phase = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-2.6 * u)
        freq = 34.0 + 105.0 * math.exp(-5.5 * u)
        phase += 2.0 * math.pi * freq / sr
        val = (0.75 * math.sin(phase) + 0.30 * math.sin(2.0 * phase) + 0.12 * math.sin(3.0 * phase)) * env
        add_sample(start_idx + k, val * 0.84 * intensity)

    elif ctype == "horn":
      dur = 1.35
      n = int(dur * sr)
      for k in range(n):
        u = k / n
        t_s = k / sr
        env = (math.sin(math.pi * u) ** 0.7) * math.exp(-1.2 * t_s)
        f0 = 65.41
        brass = (
            0.38 * math.sin(2.0 * math.pi * f0 * t_s)
            + 0.30 * math.sin(2.0 * math.pi * (f0 * 2.003) * t_s)
            + 0.20 * math.sin(2.0 * math.pi * (f0 * 3.006) * t_s)
            + 0.12 * math.sin(2.0 * math.pi * (f0 * 4.0) * t_s)
        )
        add_sample(start_idx + k, brass * env * 0.74 * intensity)

    elif ctype == "cannon":
      dur = 1.3
      n = int(dur * sr)
      phase = 0.0
      lp = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-3.2 * u)
        freq = 32.0 + 110.0 * math.exp(-22.0 * u)
        phase += 2.0 * math.pi * freq / sr
        noise = rng.random() * 2.0 - 1.0
        lp = 0.93 * lp + 0.07 * noise
        crack = noise * math.exp(-38.0 * u)
        val = (0.65 * math.tanh(1.5 * math.sin(phase)) + 0.55 * lp + 0.40 * crack) * env
        add_sample(start_idx + k, val * 0.86 * intensity)

    elif ctype == "clock":
      for tick_i in range(4):
        t_offset = int(tick_i * 0.24 * sr)
        dur = 0.055
        n = int(dur * sr)
        f_tick = 1150.0 if tick_i % 2 == 0 else 860.0
        for k in range(n):
          u = k / sr
          env = math.exp(-75.0 * u)
          click = (rng.random() * 2.0 - 1.0) * math.exp(-140.0 * u)
          val = (
              0.7 * math.sin(2.0 * math.pi * f_tick * u)
              + 0.3 * math.sin(2.0 * math.pi * (f_tick * 2.4) * u)
              + 0.4 * click
          ) * env
          add_sample(start_idx + t_offset + k, val * 0.65 * intensity)

    elif ctype == "typewriter":
      for blip_i in range(3):
        t_offset = int(blip_i * 0.065 * sr)
        dur = 0.045
        n = int(dur * sr)
        f_blip = 1480.0 + (blip_i * 180.0)
        for k in range(n):
          u = k / sr
          env = math.exp(-65.0 * u)
          mech = (rng.random() * 2.0 - 1.0) * math.exp(-120.0 * u)
          val = (0.65 * math.sin(2.0 * math.pi * f_blip * u) + 0.35 * mech) * env
          add_sample(start_idx + t_offset + k, val * 0.54 * intensity)

    elif ctype == "shimmer":
      dur = 0.75
      n = int(dur * sr)
      freqs = [1567.98, 2093.00, 2637.02, 3135.96, 4186.01]
      for k in range(n):
        u = k / sr
        env = math.exp(-6.5 * u)
        bell = sum(
            math.sin(2.0 * math.pi * f * u) * math.exp(-i * 1.5 * u)
            for i, f in enumerate(freqs)
        ) / len(freqs)
        add_sample(start_idx + k, bell * env * 0.58 * intensity)

    elif ctype == "whoosh":
      dur = 0.36
      n = int(dur * sr)
      lp = 0.0
      phase = 0.0
      for k in range(n):
        u = k / n
        env = math.sin(math.pi * u) ** 1.6
        alpha = 0.04 + 0.38 * math.sin(math.pi * u)
        noise = rng.random() * 2.0 - 1.0
        lp = (1.0 - alpha) * lp + alpha * noise
        freq = 140.0 + 260.0 * math.sin(math.pi * u)
        phase += 2.0 * math.pi * freq / sr
        val = (0.75 * lp + 0.25 * math.sin(phase)) * env
        add_sample(start_idx + k, val * 0.72 * intensity)

    elif ctype == "swoosh":
      dur = 0.22
      n = int(dur * sr)
      lp = 0.0
      for k in range(n):
        u = k / n
        env = math.sin(math.pi * u) ** 2.0
        alpha = 0.08 + 0.45 * u
        noise = rng.random() * 2.0 - 1.0
        lp = (1.0 - alpha) * lp + alpha * noise
        add_sample(start_idx + k, lp * env * 0.54 * intensity)

    elif ctype == "sword":
      dur = 0.45
      n = int(dur * sr)
      freqs = [1180.0, 1740.0, 2490.0, 3310.0, 4120.0]
      for k in range(n):
        u = k / sr
        env = math.exp(-11.0 * u)
        ring = sum(math.sin(2.0 * math.pi * f * u) for f in freqs) / len(freqs)
        burst = (rng.random() * 2.0 - 1.0) * math.exp(-45.0 * u)
        val = (0.7 * ring + 0.5 * burst) * env
        add_sample(start_idx + k, val * 0.66 * intensity)

    elif ctype == "march":
      for step_offset in (0.0, 0.22):
        s_idx = start_idx + int(step_offset * sr)
        dur = 0.14
        n = int(dur * sr)
        phase = 0.0
        lp = 0.0
        for k in range(n):
          u = k / sr
          env = math.exp(-26.0 * u)
          freq = 75.0 + 80.0 * math.exp(-35.0 * u)
          phase += 2.0 * math.pi * freq / sr
          noise = rng.random() * 2.0 - 1.0
          lp = 0.75 * lp + 0.25 * noise
          val = (0.65 * math.sin(phase) + 0.35 * lp) * env
          add_sample(s_idx + k, val * 0.56 * intensity)

    elif ctype == "map":
      dur = 0.28
      n = int(dur * sr)
      lp = 0.0
      phase = 0.0
      for k in range(n):
        u = k / n
        env = math.sin(math.pi * u)
        noise = rng.random() * 2.0 - 1.0
        lp = 0.65 * lp + 0.35 * noise
        freq = 380.0 + 420.0 * u
        phase += 2.0 * math.pi * freq / sr
        val = (0.6 * lp + 0.4 * math.sin(phase)) * env
        add_sample(start_idx + k, val * 0.50 * intensity)

    elif ctype == "fire":
      dur = 1.0
      n = int(dur * sr)
      lp = 0.0
      for k in range(n):
        u = k / n
        env = math.sin(math.pi * u)
        noise = rng.random() * 2.0 - 1.0
        lp = 0.92 * lp + 0.08 * noise
        crackle = (rng.random() * 2.0 - 1.0) if rng.random() < 0.018 else 0.0
        val = (0.5 * lp + 0.5 * crackle) * env
        add_sample(start_idx + k, val * 0.36 * intensity)

    elif ctype == "pop":
      dur = 0.11
      n = int(dur * sr)
      phase = 0.0
      for k in range(n):
        u = k / sr
        env = math.exp(-32.0 * u)
        freq = 320.0 + 520.0 * math.exp(-40.0 * u)
        phase += 2.0 * math.pi * freq / sr
        val = math.sin(phase) * env
        add_sample(start_idx + k, val * 0.60 * intensity)

    elif ctype == "riser":
      dur = 0.95
      n = int(dur * sr)
      phase = 0.0
      lp = 0.0
      for k in range(n):
        u = k / n
        env = (u**2.2) * math.sin(math.pi * min(u * 1.05, 1.0))
        freq = 120.0 + 680.0 * (u**2)
        phase += 2.0 * math.pi * freq / sr
        noise = rng.random() * 2.0 - 1.0
        lp = 0.80 * lp + 0.20 * noise
        val = (0.6 * math.sin(phase) + 0.4 * lp) * env
        add_sample(start_idx + k, val * 0.54 * intensity)

  _write_wav_from_floats(buf, sr, out_wav)


def render(i):
  from playwright.sync_api import sync_playwright

  with open(f"{IN_DIR}/chunks.json", encoding="utf-8") as f:
    raw_chunks = json.load(f)

  meta = {}
  for idx_pos, item in enumerate(raw_chunks):
    key = item.get("index", idx_pos)
    meta[int(key)] = item

  if i not in meta:
    raise SystemExit(f"Chunk index {i} not found in {IN_DIR}/chunks.json")

  chunk_meta = meta[i]
  duration = float(chunk_meta["duration"])
  frames = max(1, round(duration * FPS))

  hyphen_scene = os.path.abspath(f"{IN_DIR}/scene-{i}.html")
  scene = os.path.abspath(f"{IN_DIR}/scene_{i}.html")
  if os.path.exists(hyphen_scene) and not os.path.exists(scene):
    os.rename(hyphen_scene, scene)

  audio = f"{IN_DIR}/audio_{i}.mp3"
  os.makedirs(OUT_DIR, exist_ok=True)
  video = f"{OUT_DIR}/video_{i}.mp4"
  bgm_wav = f"{OUT_DIR}/bgm_{i}.wav"
  sfx_wav = f"{OUT_DIR}/sfx_{i}.wav"
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

  # Opening viral hook: 808 Bass Drop + Boom at 0ms
  auto_cues = [
      {"time_ms": 0, "type": "bass_drop", "intensity": 0.98},
      {"time_ms": 20, "type": "boom", "intensity": 0.90},
  ]
  auto_cues.extend(extract_timeline_cues(chunk_meta))

  prev_state = None

  with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
        viewport={"width": WIDTH, "height": HEIGHT},
        device_scale_factor=SCALE,
    )
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(INIT_JS)
    page.goto("file://" + scene, wait_until="load")
    page.wait_for_timeout(400)

    for f in range(frames):
      t = f * 1000.0 / FPS
      state = page.evaluate(STEP_JS, t)

      if isinstance(state, dict) and prev_state is not None:
        if state["shots"] != prev_state["shots"]:
          if t > 950:
            auto_cues.append(
                {"time_ms": round(t - 850), "type": "riser", "intensity": 0.65}
            )
          auto_cues.append(
              {"time_ms": round(t), "type": "whoosh", "intensity": 0.90}
          )
        else:
          if state["texts"] != prev_state["texts"] and len(
              state["texts"]
          ) > len(prev_state["texts"]):
            if re.search(r"\d", state["texts"]):
              auto_cues.append(
                  {"time_ms": round(t), "type": "typewriter", "intensity": 0.80}
              )
            else:
              auto_cues.append(
                  {"time_ms": round(t), "type": "pop", "intensity": 0.80}
              )
          elif state["visibleCount"] - prev_state["visibleCount"] >= 4:
            auto_cues.append(
                {"time_ms": round(t), "type": "pop", "intensity": 0.68}
            )

          cam_delta = math.hypot(
              state["camX"] - prev_state["camX"],
              state["camY"] - prev_state["camY"],
          )
          scale_delta = abs(state["camScale"] - prev_state["camScale"])
          if cam_delta > 28.0 or scale_delta > 0.08:
            auto_cues.append(
                {"time_ms": round(t), "type": "boom", "intensity": 0.82}
            )
          elif cam_delta > 9.0 or scale_delta > 0.022:
            auto_cues.append(
                {"time_ms": round(t), "type": "swoosh", "intensity": 0.70}
            )

          limb_delta = abs(state["limbAngles"] - prev_state["limbAngles"])
          if limb_delta > 18.0:
            auto_cues.append(
                {"time_ms": round(t), "type": "sword", "intensity": 0.78}
            )
          elif limb_delta > 8.5:
            auto_cues.append(
                {"time_ms": round(t), "type": "swoosh", "intensity": 0.56}
            )

          leg_delta = abs(state["legMotion"] - prev_state["legMotion"])
          if leg_delta > 6.0:
            auto_cues.append(
                {"time_ms": round(t), "type": "march", "intensity": 0.66}
            )

          map_delta = abs(state["mapProgress"] - prev_state["mapProgress"])
          if map_delta > 15:
            auto_cues.append(
                {"time_ms": round(t), "type": "map", "intensity": 0.66}
            )

          if state["hasFire"] and f % 30 == 0:
            auto_cues.append(
                {"time_ms": round(t), "type": "fire", "intensity": 0.54}
            )

          if state["hasCrownOrGold"] and not prev_state.get("hasCrownOrGold"):
            auto_cues.append(
                {"time_ms": round(t), "type": "shimmer", "intensity": 0.74}
            )

      prev_state = state if isinstance(state, dict) else prev_state

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

  print(
      f"  Auto-detected {len(auto_cues)} raw visual/timeline events!"
      " Synthesizing Separate BGM & 14-SFX Tracks...",
      flush=True,
  )
  generate_bgm_wav(duration, bgm_wav)
  generate_sfx_wav(duration, auto_cues, sfx_wav, seed=i)

  if os.path.exists(audio):
    # Separate BGM (ducked under VO) + Punchy SFX + Voiceover
    filter_graph = (
        f"[1:a]volume=1.08,apad=whole_dur={duration},asplit=2[vo][sc];"
        f"[2:a]volume=0.34[bg_raw];"
        f"[bg_raw][sc]sidechaincompress=threshold=0.03:ratio=4.0:attack=15:release=240[bg_ducked];"
        f"[3:a]volume=0.68[sfx];"
        f"[vo][bg_ducked][sfx]amix=inputs=3:duration=first:dropout_transition=0:weights=1.25 0.65 0.95,"
        f"alimiter=limit=0.96[aout]"
    )
    res = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video,
            "-i",
            audio,
            "-i",
            bgm_wav,
            "-i",
            sfx_wav,
            "-filter_complex",
            filter_graph,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            final,
        ],
        check=False,
    )
    if res.returncode != 0:
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
              "-i",
              bgm_wav,
              "-i",
              sfx_wav,
              "-filter_complex",
              f"[1:a]volume=1.08,apad=whole_dur={duration}[vo];[2:a]volume=0.28[bg];[3:a]volume=0.62[sfx];[vo][bg][sfx]amix=inputs=3:duration=first:dropout_transition=0,volume=1.85,alimiter=limit=0.95[aout]",
              "-map",
              "0:v",
              "-map",
              "[aout]",
              "-c:v",
              "copy",
              "-c:a",
              "aac",
              "-b:a",
              "192k",
              "-t",
              str(duration),
              final,
          ],
          check=True,
      )
  else:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video,
            "-i",
            bgm_wav,
            "-i",
            sfx_wav,
            "-filter_complex",
            f"[1:a]volume=0.45[bg];[2:a]volume=0.75[sfx];[bg][sfx]amix=inputs=2:duration=first:dropout_transition=0,volume=1.6,alimiter=limit=0.95[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            final,
        ],
        check=True,
    )

  for temp_file in (video, bgm_wav, sfx_wav):
    if os.path.exists(temp_file):
      os.remove(temp_file)

  print(
      f"Saved {final} (with Ducked BGM, Punchy 14-SFX & Full Loudness)",
      flush=True,
  )


def _clip_index(path):
  m = re.search(r"synced_(\d+)\.mp4$", os.path.basename(path))
  return int(m.group(1)) if m else 0


def merge():
  files = glob.glob(f"{OUT_DIR}/synced_*.mp4")
  files.sort(key=_clip_index)
  if not files:
    raise SystemExit("No clips found to merge")

  concat_path = "concat.txt"
  with open(concat_path, "w", encoding="utf-8") as f:
    for p in files:
      safe_path = os.path.abspath(p).replace("'", "'\\''")
      f.write(f"file '{safe_path}'\n")

  try:
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
            concat_path,
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
  finally:
    if os.path.exists(concat_path):
      os.remove(concat_path)

  print(f"Merged {len(files)} clips -> final_shorts.mp4 (1080x1920)", flush=True)


if __name__ == "__main__":
  if len(sys.argv) < 2:
    raise SystemExit("usage: render_shorts_scenes.py render N | merge")
  mode = sys.argv[1]
  if mode == "render":
    if len(sys.argv) < 3:
      raise SystemExit("usage: render_shorts_scenes.py render N")
    render(int(sys.argv[2]))
  elif mode == "merge":
    merge()
  else:
    raise SystemExit("usage: render_shorts_scenes.py render N | merge")
