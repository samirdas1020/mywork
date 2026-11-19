"""sfx_engine.py - dynamic sound effects + background music, derived from the scene itself.

No hardcoded ids, no keyword rules. The scene is stepped frame by frame (same stepping the
renderer uses), every element's visibility / geometry / text is recorded, and events are
found with statistics of the scene's OWN signals. Sounds are synthesized from each event's
measured properties (size, speed, direction, position, suddenness). Requires numpy only
(Pillow optional, for colour-based music mood).
"""
import hashlib, io, json, os, subprocess, wave
import numpy as np

SR = 44100

# ---------------------------------------------------------------- 1. scene probe (in page)
PROBE_JS = r"""(a) => {
  const step = eval('(' + a.step + ')');
  const skip = new Set(['script','style','defs','lineargradient','radialgradient','stop','filter',
    'fedropshadow','title','meta','clippath','mask','pattern','symbol','marker','link','head']);
  const nodes = [], parent = [];
  const walk = (el, pi) => { for (const c of el.children) {
    if (skip.has(c.tagName.toLowerCase())) continue;
    const i = nodes.length; nodes.push(c); parent.push(pi); walk(c, i); } };
  walk(document.body, -1);
  const N = nodes.length, F = a.frames;
  const mk = () => new Float32Array(N * F).fill(NaN);
  const VIS = mk(), CX = mk(), CY = mk(), W = mk(), H = mk();
  const leaf = nodes.map(n => n.children.length === 0);
  const lastTxt = nodes.map((n, i) => leaf[i] ? (n.textContent || '') : null);
  const texts = [], eff = new Float32Array(N);
  for (let f = 0; f < F; f++) {
    step(f * 1000 / a.fps);
    for (let i = 0; i < N; i++) {
      const p = parent[i], pe = p < 0 ? 1 : eff[p], k = i * F + f;
      eff[i] = 0;
      if (pe === 0) { VIS[k] = 0; continue; }
      const n = nodes[i], cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') { VIS[k] = 0; continue; }
      const o = pe * parseFloat(cs.opacity);
      eff[i] = o; VIS[k] = o;
      let r = null;
      if (o > 0) {
        r = n.getBoundingClientRect();
        if (r.width > 0 || r.height > 0) {
          CX[k] = r.left + r.width / 2; CY[k] = r.top + r.height / 2; W[k] = r.width; H[k] = r.height;
        }
      }
      if (leaf[i]) {
        const tx = n.textContent || '';
        if (tx !== lastTxt[i]) {
          if (o > 0 && tx.trim() && r) texts.push({f, i, text: tx.trim().slice(0, 40),
            cx: r.left + r.width / 2, cy: r.top + r.height / 2, area: r.width * r.height});
          lastTxt[i] = tx;
        }
      }
    }
  }
  const rng = (A, i) => { let lo = Infinity, hi = -Infinity;
    for (let f = 0; f < F; f++) { const v = A[i * F + f]; if (v === v) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    return hi - lo; };
  const rd = (A, i, d) => Array.from(A.subarray(i * F, (i + 1) * F), v => v !== v ? null : Math.round(v * d) / d);
  const els = [];
  for (let i = 0; i < N; i++) {
    let vmax = 0; for (let f = 0; f < F; f++) vmax = Math.max(vmax, VIS[i * F + f]);
    if (vmax <= 0) continue;
    const changes = rng(VIS, i) > 0.01 || rng(CX, i) > 0.2 || rng(CY, i) > 0.2 || rng(W, i) > 0.2 || rng(H, i) > 0.2;
    if (!changes) continue;
    els.push({id: nodes[i].id || (nodes[i].tagName + '#' + i), i,
      vis: rd(VIS, i, 100), cx: rd(CX, i, 10), cy: rd(CY, i, 10), w: rd(W, i, 10), h: rd(H, i, 10)});
  }
  return {vw: innerWidth, vh: innerHeight, frames: F, fps: a.fps, els, texts};
}"""


def analyze(page, step_js, frames, fps):
    """Step the scene (no screenshots) and return raw per-element signals."""
    return page.evaluate(PROBE_JS, {"step": step_js, "frames": int(frames), "fps": fps})


# ---------------------------------------------------------------- 2. event detection
# Per-kind weights are taste knobs for the mix, NOT detection rules.
CUT_SOUND = False  # False = no sound at shot changes (cuts still steer the music beat)
WHOOSH = False  # True = use swept-noise whoosh for cuts/jumps; False = soft thump / pop
PRIOR = dict(cut=1.0, appear=0.7, text=0.9, jump=0.8, stop=0.9, bounce=1.0, shake=0.8)


def _loud(raw):
    """raw 0..1 -> loudness 0..1 on a dB scale (-54 dB .. 0 dB); hearing is logarithmic."""
    return float(np.clip((20 * np.log10(max(raw, 1e-6)) + 54) / 54, 0, 1))


def _mad(x):
    m = np.median(x)
    return m, np.median(np.abs(x - m))


def _shake_segments(gx, gy, fps):
    F = len(gx)
    e = np.hypot(gx, gy)
    med, mad = _mad(e)
    thr = med + 5 * max(mad, 2.0)                       # 2px = render noise floor
    hot = e > thr
    sx, sy = np.sign(gx), np.sign(gy)
    flip = np.zeros(F, bool)
    flip[1:] = ((sx[1:] * sx[:-1]) < 0) | ((sy[1:] * sy[:-1]) < 0)
    segs, f = [], 0
    while f < F:
        if not hot[f]:
            f += 1
            continue
        s, last = f, f
        while f < F and (f - last) <= 2:
            if hot[f]:
                last = f
            f += 1
        n = last - s + 1
        if n >= 6 and flip[s:last + 1].sum() >= 0.3 * n:
            segs.append((s, last, float(np.sqrt(np.mean(e[s:last + 1] ** 2))),
                         float(flip[s:last + 1].sum() / 2 / (n / fps))))
    return segs


def detect(data, fps):
    VW, VH, F = data["vw"], data["vh"], data["frames"]
    diag, area0 = float(np.hypot(VW, VH)), float(VW * VH)
    eps = 1.5                                            # px, sub-pixel render noise
    els = []
    for e in data["els"]:
        A = {k: np.array(e[k], float) for k in ("vis", "cx", "cy", "w", "h")}
        A["id"] = e["id"]
        A["area"] = np.nan_to_num(A["w"] * A["h"]) / area0
        els.append(A)
    nE = len(els)
    ev = []

    # --- global camera motion + shake segments
    DX = np.full((max(nE, 1), F), np.nan)
    DY = DX.copy()
    for k, A in enumerate(els):
        DX[k, 1:] = np.diff(A["cx"])
        DY[k, 1:] = np.diff(A["cy"])
    valid = np.isfinite(DX).sum(axis=0)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gx = np.nan_to_num(np.nanmedian(DX, axis=0))
        gy = np.nan_to_num(np.nanmedian(DY, axis=0))
    gx[valid < 4], gy[valid < 4] = 0, 0
    segs = _shake_segments(gx, gy, fps)
    in_shake = np.zeros(F, bool)
    for s, l, amp, fr in segs:
        in_shake[max(0, s - 1):l + 2] = True
        ev.append(dict(f=s, kind="shake", I=float(np.clip(amp / diag / 0.004, 0.25, 1)),
                       x=0.5, y=0.5, dx=0, dy=0, dur=(l - s + 1) * 1000 / fps,
                       freq=float(np.clip(fr, 3, 12)), area=1.0))

    # --- per element
    for k, A in enumerate(els):
        vis, cx, cy, area = A["vis"], A["cx"], A["cy"], A["area"]
        vmax = np.nanmax(vis)
        if vmax > 0.02:                                  # appear: relative to own range
            v = np.nan_to_num(vis) / vmax
            on = v > 0.5
            for f in range(1, F):
                if on[f] and not on[f - 1]:
                    j = f - 1
                    while j > 0 and v[j] > 0.2:
                        j -= 1
                    sud = 1.0 / (1.0 + (f - j) / 3.0)
                    a = float(np.max(area[f:f + 8]))
                    ev.append(dict(f=f, kind="appear", area=a, sud=sud,
                                   x=float(np.nan_to_num(cx[f], nan=VW / 2) / VW),
                                   y=float(np.nan_to_num(cy[f], nan=VH / 2) / VH), dx=0, dy=0))
        dx, dy = DX[k].copy(), DY[k].copy()
        dx[in_shake & np.isfinite(dx)] -= gx[in_shake & np.isfinite(dx)]
        dy[in_shake & np.isfinite(dy)] -= gy[in_shake & np.isfinite(dy)]
        dw = np.r_[np.nan, np.diff(A["w"])]
        dh = np.r_[np.nan, np.diff(A["h"])]
        m = np.hypot(dx, dy) + 0.5 * (np.abs(dw) + np.abs(dh))
        ok = np.isfinite(m)
        if ok.sum() < 3:
            continue
        nz = m[ok & (m > eps)]
        if len(nz) == 0:
            continue
        med, mad = _mad(nz)
        thr = med + 6 * max(mad, 0.25 * med) if len(nz) >= 3 else 8 * eps
        hi = np.percentile(nz, 75) if len(nz) >= 4 else None
        for f in range(1, F):
            if not ok[f] or in_shake[f]:                 # inside a shake the residual is jitter
                continue
            ux, uy = dx[f], dy[f]
            nrm = max(np.hypot(ux, uy), 1e-9)
            base = dict(f=f, area=float(area[f]), x=float(cx[f] / VW), y=float(cy[f] / VH),
                        dx=float(ux / nrm), dy=float(uy / nrm))
            if m[f] > max(thr, 3 * eps) and (f == 1 or not ok[f - 1] or m[f - 1] <= thr):
                ev.append(dict(base, kind="jump", mag=float(m[f] / diag)))
            if hi is not None and f >= 2 and ok[f - 1]:
                p, c = m[f - 1], m[f]
                if p >= max(hi, 3 * eps) and p <= thr and c < 0.2 * p:
                    ev.append(dict(base, kind="stop", mag=float(p / diag)))
                elif (p >= 0.5 * hi and c >= 0.5 * hi and p > 3 * eps and
                      dx[f - 1] * dx[f] + dy[f - 1] * dy[f] < 0):
                    ev.append(dict(base, kind="bounce", mag=float(c / diag)))

    # --- text changes
    for t in data["texts"]:
        ev.append(dict(f=t["f"], kind="text", area=t["area"] / area0, x=t["cx"] / VW,
                       y=t["cy"] / VH, dx=0, dy=0, text=t["text"]))

    # --- importance from measured size / speed / suddenness, mapped to loudness in dB
    for e in ev:
        k = e["kind"]
        if k != "shake":
            a = float(np.clip(e.get("area", 0), 0, 1))
            s = np.sqrt(a)
            e["size"] = s
            if k == "appear":
                raw = s * (0.35 + 0.65 * e["sud"])
            elif k == "text":
                raw = 0.35 + 0.65 * s
            else:
                raw = s * (0.3 + 0.7 * min(1.0, e["mag"] / 0.08))
            e["I"] = _loud(raw * PRIOR[k])
        else:
            e["size"] = 0.8
            e["I"] = _loud(e["I"] * PRIOR[k])
    return _cluster(ev, fps, F)


def _cluster(ev, fps, F):
    sustained = [e for e in ev if e["kind"] == "shake"]
    ev = sorted([e for e in ev if e["kind"] != "shake"], key=lambda e: e["f"])
    win = max(1, round(0.1 * fps))
    groups, cur = [], []
    for e in ev:
        if cur and e["f"] - cur[0]["f"] > win:           # anchored window: no chaining
            groups.append(cur)
            cur = []
        cur.append(e)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        top = max(g, key=lambda e: e["I"])
        ap = [e for e in g if e["kind"] == "appear"]
        asum = min(1.0, sum(e["area"] for e in ap))
        o = dict(top)
        if asum >= 0.5:                                  # half the viewport changed at once
            o["kind"], o["I"], o["size"] = "cut", _loud(float(np.sqrt(asum))), 1.0
            o["x"], o["y"], o["dx"], o["dy"] = 0.5, 0.5, 0.0, 0.0
            o["t"] = round(float(np.median([e["f"] for e in ap])) / fps, 3)
            for tx in (e for e in g if e["kind"] == "text"):
                out.append(dict(tx, t=o["t"], n=1))
        else:
            o["t"] = round(top["f"] / fps, 3)
        o["n"] = len(g)
        out.append(o)
    for e in sustained:
        e["t"], e["n"] = round(e["f"] / fps, 3), 1
        out.append(e)
    out.sort(key=lambda e: e["t"])
    return out


def select(events, dur_s):
    """Keep the strongest events; neighbours are masked in proportion to importance."""
    if not events:
        return []
    cand = sorted([e for e in events if e["I"] >= 0.35], key=lambda e: -e["I"])  # >-35 dB
    keep = []
    for e in cand:
        if e["kind"] == "shake" or all(
                k["kind"] == "shake" or (k["kind"] == "cut" and not CUT_SOUND) or abs(e["t"] - k["t"]) >= 0.15 + 0.45 * max(e["I"], k["I"])
                for k in keep):
            keep.append(e)
    keep.sort(key=lambda e: e["t"])
    clean = []
    for e in keep:
        clean.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in e.items()
                      if k not in ("f", "area", "sud", "mag")})
    return clean


def find_events(page, step_js, frames, fps):
    data = analyze(page, step_js, frames, fps)
    return select(detect(data, fps), frames / fps)


# ---------------------------------------------------------------- 3. synthesis
def _box(x, win):
    win = max(1, int(win))
    return x if win == 1 else np.convolve(x, np.ones(win) / win, "same")


def voice(dur, f0, f1, tone, noise, b0, b1, attack, power, rng, wob=0.0):
    n = max(8, int(dur * SR))
    t = np.arange(n) / SR
    u = t / dur
    f = f0 * (f1 / f0) ** u
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = tone * (np.sin(ph) + 0.25 * np.sin(2 * ph))
    if noise > 0:
        z = rng.standard_normal(n)
        lo = _box(z, 1 + (1 - b0) * 80)
        hi = _box(z, 1 + (1 - b1) * 80)
        ramp = np.clip(u, 0, 1)
        z = lo * (1 - ramp) + hi * ramp
        z /= np.abs(z).max() + 1e-9
        sig = sig + noise * z
    env = np.minimum(1, t / max(attack, 1e-3)) * np.clip(1 - u, 0, 1) ** power
    if wob:
        env = env * (0.65 + 0.35 * np.sin(2 * np.pi * wob * t))
    out = sig * env
    out = out / (np.abs(out).max() + 1e-9)
    return np.tanh(2.2 * out) / np.tanh(2.2)             # raise RMS so short sounds are heard


def _sweep_bandpass(x, fc, q):
    """Resonant band-pass (state-variable filter) with a moving centre frequency."""
    f = 2 * np.sin(np.pi * np.minimum(fc, 6000) / SR)
    qq, low, band = 1.0 / q, 0.0, 0.0
    out = np.empty_like(x)
    for i in range(len(x)):
        low += f[i] * band
        band += f[i] * (x[i] - low - qq * band)
        out[i] = band
    return out


def whoosh(dur, rising, size, rng):
    """Airy pass-by: band-limited noise whose centre sweeps, with a soft body and smooth swell."""
    n = int(dur * SR)
    u = np.arange(n) / n
    lo, hi = 220 + 200 * (1 - size), 1500 + 2200 * (1 - size)    # bigger => darker
    fc = lo * (hi / lo) ** (u if rising else 1 - u)
    z = rng.standard_normal(n)
    air = _sweep_bandpass(z, fc, 2.2)
    air /= np.abs(air).max() + 1e-9
    body = _box(rng.standard_normal(n), 60)                    # low "air movement"
    body /= np.abs(body).max() + 1e-9
    sig = air + 0.35 * body
    a = 1.35 if rising else 0.75                                # builds up, then passes
    env = np.sin(np.pi * np.clip(u, 0, 1) ** a) ** 1.6
    fade = np.minimum(1, np.arange(n) / (0.01 * SR)) * np.minimum(1, np.arange(n)[::-1] / (0.03 * SR))
    out = sig * env * fade
    return out / (np.abs(out).max() + 1e-9)


# ---- building blocks: different timbres, not just tones -------------------------------
def _sum(*parts):
    """parts = (array, gain, delay_seconds)"""
    n = max(int(d * SR) + len(x) for x, g, d in parts)
    out = np.zeros(n)
    for x, g, d in parts:
        i = int(d * SR)
        out[i:i + len(x)] += x * g
    return out


def _norm(x):
    return x / (np.abs(x).max() + 1e-9)


def _reverb(x, rt60, wet, rng):
    """Room/hall tail: convolve with decaying, progressively darker noise."""
    n = int(rt60 * 1.1 * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    ir = 0.4 * ir + 0.6 * _box(ir, 30)
    m = len(x) + n - 1
    L = 1 << (m - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, L) * np.fft.rfft(ir, L), L)[:m]
    y = y / (np.abs(y).max() + 1e-9) * wet * np.abs(x).max()
    out = np.zeros(m)
    out[:len(x)] = x
    return out + y


def _click(rng, dur=0.015, bright=0.8):
    n = max(8, int(dur * SR))
    z = rng.standard_normal(n)
    z = z - _box(z, 2 + int((1 - bright) * 10))
    return _norm(z * np.exp(-np.arange(n) / SR / (dur / 4)))


def _q(f):
    """Snap a frequency to a major pentatonic note so pitched sounds stay consonant."""
    m = 69 + 12 * np.log2(max(f, 40) / 440.0)
    best = min((c for c in range(int(m) - 3, int(m) + 4) if c % 12 in (0, 2, 4, 7, 9)),
               key=lambda c: abs(c - m))
    return 440.0 * 2 ** ((best - 69) / 12)


def _partials(f, dur, parts, rng):
    t = np.arange(int(dur * SR)) / SR
    x = sum(a * np.sin(2 * np.pi * f * r * t + rng.uniform(0, 6.28)) * np.exp(-t / tau)
            for r, a, tau in parts)
    x[:int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return _norm(x)


def _bell(f, dur, rng):
    t = np.arange(int(dur * SR)) / SR
    idx = 3.0 * np.exp(-t / 0.25)
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 3.5 * t)) * np.exp(-t / (dur / 4))
    x += 0.3 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / (dur / 6))
    x[:int(0.001 * SR)] *= np.linspace(0, 1, int(0.001 * SR))
    return _norm(x)


def _marimba(f, dur, rng):
    return _partials(f, dur, [(1, 1, 0.22), (3.97, 0.45, 0.07), (9.9, 0.2, 0.025)], rng)


def _clink(f, dur, rng):
    x = _partials(f, dur, [(1, 1, 0.30), (2.32, 0.7, 0.18), (4.25, 0.5, 0.10), (6.63, 0.35, 0.06)], rng)
    return _sum((x, 1, 0), (_click(rng, 0.008, 0.95), 0.4, 0))


def _hit(size, I, rng):
    """Cinematic impact: click + dropping body + sub tail + dark noise burst + hall reverb."""
    f0 = 95 - 45 * size + rng.uniform(-6, 6)
    body = voice(0.5 + 0.4 * I, f0 * 2.2, f0 * 0.6, 1, 0, 0.5, 0.5, 0.002, 2.2, rng)
    sub = voice(0.7 + 0.5 * I, f0 * 0.55, f0 * 0.45, 1, 0, 0.5, 0.5, 0.01, 1.4, rng)
    tex = voice(0.35, 100, 100, 0, 1, 0.5, 0.15, 0.002, 3, rng)
    x = _norm(_sum((body, 1, 0), (sub, 0.6, 0.005), (_click(rng, 0.02, 0.9), 0.5, 0), (tex, 0.35, 0)))
    return _reverb(x, 0.6 + 0.8 * I, 0.30 + 0.2 * I, rng)


def _cut(size, I, rng):
    v = int(rng.integers(0, 3))
    if v == 0:
        return _hit(size, I, rng)
    if v == 1:                                           # low drum
        x = _norm(_sum((voice(0.35, 170, 46, 1, 0.05, 0.4, 0.3, 0.002, 2.6, rng), 1, 0),
                       (_click(rng, 0.012, 0.8), 0.45, 0)))
        return _reverb(x, 0.5, 0.25, rng)
    x = _norm(_sum((voice(1.0, 95, 34, 1, 0.12, 0.3, 0.15, 0.03, 1.1, rng), 1, 0),   # sub drop
                   (_click(rng, 0.01, 0.7), 0.25, 0)))
    return _reverb(x, 0.9, 0.3, rng)


def _snap(rng):
    n = _sum((_click(rng, 0.02, 0.8), 1, 0),
             (voice(0.14, 100, 100, 0, 1, 0.45, 0.3, 0.001, 3, rng), 0.8, 0),
             (voice(0.1, 220, 150, 1, 0, 0.5, 0.5, 0.001, 3, rng), 0.4, 0))
    return _reverb(_norm(n), 0.25, 0.15, rng)


def _appear(size, f, rng):
    pool = ["tick", "glass"] if size < 0.1 else ["marimba", "tick", "glass"]
    v = pool[int(rng.integers(0, len(pool)))]
    if v == "marimba":
        return _reverb(_marimba(f, 0.35, rng), 0.3, 0.15, rng)
    if v == "glass":
        return _reverb(_clink(f * 1.5, 0.3, rng), 0.35, 0.2, rng)
    return _norm(_sum((_click(rng, 0.01, 0.9), 1, 0),
                      (voice(0.06, f * 1.5, f, 1, 0, 0.5, 0.5, 0.001, 3, rng), 0.5, 0)))


def _knock(size, rng):
    f = 150 - 70 * size
    x = _norm(_sum((_partials(f, 0.3, [(1, 1, 0.12), (2.7, 0.4, 0.05)], rng), 1, 0),
                   (_click(rng, 0.012, 0.6), 0.5, 0)))
    return _reverb(x, 0.3, 0.2, rng)


def synth_event(e, rng):
    I, k = e["I"], e["kind"]
    size = e.get("size", I)
    f = _q(260 + 1300 * (1 - size) ** 2)                # bigger => lower; snapped to a scale
    if WHOOSH and k in ("cut", "jump"):
        rising = (e.get("dy", 0) < 0) or (e.get("dy", 0) == 0 and e.get("dx", 0) >= 0)
        return whoosh(0.28 + 0.5 * I if k == "cut" else 0.15 + 0.35 * I, rising, size, rng)
    if k == "cut":
        x = _cut(size, I, rng)
    elif k == "jump":
        x = _snap(rng)
    elif k == "appear":
        x = _appear(size, f, rng)
    elif k == "text":
        x = _reverb(_bell(f * 0.75, 0.5 + 0.5 * I, rng), 0.8, 0.3, rng)
    elif k == "bounce":
        x = _reverb(_clink(f * 1.2, 0.3, rng), 0.3, 0.15, rng) if size < 0.25 else _knock(size, rng)
    elif k == "stop":
        x = _knock(size, rng)
    elif k == "shake":
        d = min(4.0, max(0.4, e.get("dur", 1000) / 1000))
        x = voice(d, 38, 32, 0.5, 1, 0.03, 0.03, 0.15, 0.4, rng, wob=e.get("freq", 6))
    else:
        x = _click(rng, 0.02, 0.8)
    return np.tanh(1.5 * _norm(x)) / np.tanh(1.5)


def _seed(obj):
    return int(hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:8], 16)


def decode_audio(path, n):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
                        "-ar", str(SR), "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)
    out = np.zeros(n)
    out[:min(n, len(a))] = a[:n]
    return out


def mix_chunk(events, frames, fps, audio_path=None):
    """Voice + generated SFX, exactly frames/fps long. Returns float32 (n, 2)."""
    n = int(round(frames / fps * SR))
    voice_sig, env = None, None
    if audio_path and os.path.exists(audio_path):
        voice_sig = decode_audio(audio_path, n)
        w = int(0.02 * SR)
        rms = np.sqrt(np.convolve(voice_sig ** 2, np.ones(w) / w, "same"))
        rms = _box(rms, int(0.1 * SR))
        env = rms / (np.percentile(rms[rms > 1e-4], 90) + 1e-9) if (rms > 1e-4).any() else rms
        env = np.clip(env, 0, 1)
    rng = np.random.default_rng(_seed(events))
    ref = 0.5 if voice_sig is None else 1.0 * float(np.percentile(np.abs(voice_sig), 99.5) + 1e-6)
    sfx = np.zeros((n, 2))
    for e in events:
        if e["kind"] == "cut" and not CUT_SOUND:
            continue
        s = synth_event(e, rng)
        i0 = int(e["t"] * SR)
        if i0 >= n:
            continue
        g = ref * (0.3 + 0.7 * e["I"])
        if env is not None:
            i1 = min(n, i0 + max(1, int(0.2 * SR)))
            g *= 1 - 0.3 * float(env[i0:i1].mean())
        pan = float(np.clip(e.get("x", 0.5), 0, 1)) * np.pi / 2
        seg = s[:n - i0] * g
        sfx[i0:i0 + len(seg), 0] += seg * np.cos(pan)
        sfx[i0:i0 + len(seg), 1] += seg * np.sin(pan)
    out = sfx * 1.4142 / 1.4142
    if voice_sig is not None:
        out += voice_sig[:, None]
    pk = np.abs(out).max()
    if pk > 0.98:
        out *= 0.98 / pk
    return out.astype(np.float32)


# ---------------------------------------------------------------- 4. colour features + metadata
def sample_color(jpeg_bytes):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(jpeg_bytes))
        im.draft("RGB", (96, 170))
        a = np.asarray(im.convert("RGB").resize((24, 40)), float).reshape(-1, 3).mean(0) / 255
        return [float(0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]), float(a[0] - a[2]),
                float(a.max() - a.min())]
    except Exception:
        return None


def save_meta(path, events, colors, duration):
    cs = [c for c in colors if c]
    f = np.mean(cs, axis=0).tolist() if cs else [0.4, 0.0, 0.3]
    json.dump(dict(duration=duration, events=events, lum=f[0], warm=f[1], sat=f[2]),
              open(path, "w"), indent=1)


def write_wav(path, stereo):
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- 5. background music
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
PROG_MINOR = [[0, 5, 2, 6], [0, 3, 4, 3], [0, 6, 5, 6], [0, 5, 3, 6]]
PROG_MAJOR = [[0, 4, 5, 3], [0, 5, 3, 4], [0, 3, 4, 4], [0, 4, 3, 4]]


def collect(clip_dir, files, durations):
    """Global (cut times, accent times, event times, features) from per-clip sfx_N.json."""
    cuts, acc, times, lum, warm, tot = [], [], [], 0.0, 0.0, 0.0
    off = 0.0
    for fpath, d in zip(files, durations):
        n = "".join(ch for ch in os.path.basename(fpath) if ch.isdigit())
        mp = os.path.join(clip_dir, f"sfx_{n}.json")
        if os.path.exists(mp):
            m = json.load(open(mp))
            for e in m["events"]:
                g = off + e["t"]
                times.append(g)
                if e["kind"] == "cut":
                    cuts.append(g)
                elif e["I"] >= 0.6:
                    acc.append(g)
            lum += m["lum"] * d
            warm += m["warm"] * d
            tot += d
        off += d
    tot = max(tot, 1e-9)
    return cuts, acc, times, dict(lum=lum / tot, warm=warm / tot, act=len(times) / max(off, 1e-9))


def _note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def make_music(total, cuts, accents, times, feats):
    seed = _seed([round(x, 2) for x in times] + [round(feats["lum"], 2)])
    rng = np.random.default_rng(seed)
    act = feats["act"]
    target = 78 + 52 * min(1.0, act / 1.5)
    bpms = np.arange(72, 141, 0.5)
    align = np.r_[cuts, accents]
    w = np.r_[np.full(len(cuts), 1.0), np.full(len(accents), 0.4)]
    if len(align):
        beat = align[None, :] * bpms[:, None] / 60.0
        cost = (np.abs(beat - np.round(beat)) * w[None, :]).sum(1) / w.sum()
    else:
        cost = np.zeros(len(bpms))
    bpm = float(bpms[np.argmin(cost + 0.002 * np.abs(bpms - target))])
    minor = (feats["lum"] + 0.35 * feats["warm"]) < 0.42
    scale = MINOR if minor else MAJOR
    prog = (PROG_MINOR if minor else PROG_MAJOR)[int(rng.integers(0, 4))]
    root = 45 + int(rng.integers(0, 12))
    beat_s = 60.0 / bpm
    bar = 4 * beat_s
    nb = int(np.ceil(total / bar)) + 1
    N = int((nb * bar + 1) * SR)
    L, R = np.zeros(N), np.zeros(N)

    cnt = np.histogram(times, bins=np.arange(0, nb + 1) * bar)[0].astype(float)
    cnt = np.convolve(cnt, [0.25, 0.5, 0.25], "same")
    energy = 0.25 + 0.75 * cnt / max(cnt.max(), 1e-9)

    def add(sig, t0, g, pan=0.5):
        i = int(t0 * SR)
        if i >= N:
            return
        s = sig[:N - i] * g
        L[i:i + len(s)] += s * np.cos(pan * np.pi / 2)
        R[i:i + len(s)] += s * np.sin(pan * np.pi / 2)

    def deg_midi(d, base):
        return base + scale[d % 7] + 12 * (d // 7)

    def tone(f, dur, harm, power):
        t = np.arange(int(dur * SR)) / SR
        s = sum(np.sin(2 * np.pi * f * (h + 1) * t) * a for h, a in enumerate(harm))
        return s * np.clip(1 - t / dur, 0, 1) ** power

    for b in range(nb):
        d0 = prog[b % 4]
        e = energy[b] if b < len(energy) else 0.3
        t0 = b * bar
        # pad: detuned stacked harmonics, hann-shaped, left/right slightly different
        tt = np.arange(int(bar * 1.15 * SR)) / SR
        hann = np.clip(np.sin(np.pi * tt / tt[-1]), 0, None) ** 0.8
        for side, det in ((0, 0.997), (1, 1.003)):
            pad = np.zeros_like(tt)
            for kk in (0, 2, 4):
                f = _note(deg_midi(d0 + kk, root + 12)) * det
                pad += sum(np.sin(2 * np.pi * f * (h + 1) * tt) * a
                           for h, a in enumerate((1, .5, .25, .12)))
            pad = pad / np.abs(pad).max() * hann * 0.35
            (L if side == 0 else R)[int(t0 * SR):int(t0 * SR) + len(pad)] += \
                pad[:N - int(t0 * SR)]
        # bass
        fb = _note(deg_midi(d0, root - 12))
        for bt in ([0, 2] + ([2.5] if e > 0.5 else [])):
            add(tone(fb, beat_s * 0.9, (1, .35), 1.5), t0 + bt * beat_s, 0.55)
        # drums follow the video's own activity
        if e >= 0.3:
            for bt in ([0, 1, 2, 3] if e >= 0.7 else [0, 2]):
                add(voice(0.16, 130, 45, 1, 0.05, 0.3, 0.3, 0.002, 3, rng), t0 + bt * beat_s, 0.55)
        if e >= 0.45:
            for bt in (0.5, 1.5, 2.5, 3.5):
                h = rng.standard_normal(int(0.05 * SR))
                h = (h - _box(h, 6)) * np.linspace(1, 0, len(h)) ** 2
                add(h / np.abs(h).max(), t0 + bt * beat_s, 0.16, 0.6)
        if e >= 0.6:
            for bt in (1, 3):
                add(voice(0.12, 200, 200, 0, 1, 0.7, 0.4, 0.002, 2, rng), t0 + bt * beat_s, 0.22)
        # arp on chord tones
        if e >= 0.35:
            step_n = 16 if e >= 0.8 else 8
            tones = [deg_midi(d0 + k, root + 24) for k in (0, 2, 4, 7)]
            for s in range(step_n):
                add(tone(_note(tones[s % 4]), 0.25, (1, .3), 3), t0 + s * bar / step_n,
                    0.12, 0.3 + 0.4 * (s % 2))
    out = np.stack([L, R], 1)[:int(total * SR)]
    out *= 0.6 / (np.abs(out).max() + 1e-9)
    fi, fo = int(0.4 * SR), int(1.5 * SR)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    out[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return out.astype(np.float32), dict(bpm=bpm, minor=minor, root=root)
