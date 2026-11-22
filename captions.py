"""captions.py - one-word-at-a-time captions for Shorts (English).

Word timings come from, in this order:
  1. render_input/words_N.json  (your own timings, if you already have them)
  2. faster-whisper (word timestamps) run on audio_N.mp3

The caption is drawn INTO the page just before each screenshot, so it needs no extra
video re-encode and is locked to the same frame clock as the scene. Which words get the
accent colour is decided from the voice itself (the loudest ~quarter of the words).
"""
import bisect, json, os, re
import numpy as np

# ---------------------------------------------------------------- in-page drawing
FONT_PX = 59        # caption size on the 720x1280 canvas (was 118). Change ONLY this to resize.
BOTTOM_PCT = 24     # distance from the bottom edge, in % of the height

SETUP_JS = r"""() => {
  if (document.getElementById('__cap')) return;
  const el = document.createElement('div');
  el.id = '__cap';
  el.style.cssText = 'position:fixed;left:50%;bottom:__BOTTOM__%;transform:translateX(-50%);z-index:2147483647;' +
    'display:none;pointer-events:none;white-space:nowrap;text-align:center;';
  const sp = document.createElement('span');
  sp.style.cssText = 'font-family:Montserrat,Poppins,"Arial Black",Impact,"Liberation Sans",Arial,sans-serif;' +
    'font-weight:900;font-size:__FONT__px;line-height:1.1;text-transform:uppercase;letter-spacing:0.01em;' +
    'color:#fff;-webkit-text-stroke:__STROKE__px #000;paint-order:stroke fill;' +
    'text-shadow:0 __SHADOW__px 0 rgba(0,0,0,0.55);';
  el.appendChild(sp);
  (document.body || document.documentElement).appendChild(el);
}"""

SETUP_JS = (SETUP_JS.replace('__FONT__', str(FONT_PX)).replace('__BOTTOM__', str(BOTTOM_PCT))
            .replace('__STROKE__', str(round(FONT_PX * 0.135, 1))).replace('__SHADOW__', str(round(FONT_PX * 0.068, 1))))

# a = null (hide)  or  [text, accent(bool), scale]
SET_JS = r"""(a) => {
  const el = document.getElementById('__cap');
  if (!el) return;
  if (!a) { el.style.display = 'none'; return; }
  const sp = el.firstChild, text = a[0];
  if (sp.textContent !== text) {
    sp.textContent = text;
    el.style.display = 'block';
    const w = sp.offsetWidth || 1;
    el.dataset.fit = Math.min(1, (0.9 * window.innerWidth) / w);   // long words shrink to fit
  }
  el.style.display = 'block';
  sp.style.color = a[1] ? '#FFE600' : '#FFFFFF';
  const fit = parseFloat(el.dataset.fit || '1');
  el.style.transform = 'translateX(-50%) scale(' + (fit * a[2]) + ')';
}"""


# ---------------------------------------------------------------- word timings
def _clean(w):
    w = re.sub(r"^[^\w$%#@&]+|[^\w$%]+$", "", w.strip())
    return w.upper()


def _normalise(data):
    """Accept [{word,start,end}], {"words":[...]}, or whisper-style segments with words."""
    if isinstance(data, dict):
        data = data.get("words") or data.get("segments") or []
    flat = []
    for it in data:
        if isinstance(it, dict) and "words" in it:
            flat.extend(it["words"])
        else:
            flat.append(it)
    out = []
    for w in flat:
        txt = _clean(str(w.get("word", w.get("text", ""))))
        if txt:
            out.append(dict(word=txt, start=float(w["start"]), end=float(w["end"])))
    out.sort(key=lambda x: x["start"])
    return out


def whisper_words(audio_path):
    from faster_whisper import WhisperModel          # pip install faster-whisper
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio_path, language="en", word_timestamps=True, beam_size=1)
    return [dict(word=w.word, start=w.start, end=w.end) for s in segs for w in (s.words or [])]


def load_words(audio_path, words_json):
    if words_json and os.path.exists(words_json):
        return _normalise(json.load(open(words_json, encoding="utf-8")))
    return _normalise(whisper_words(audio_path))


# ---------------------------------------------------------------- timeline
class Captions:
    HOLD = 0.25            # keep the last word this long after it ends if speech stops
    JOIN = 0.5             # gaps shorter than this are bridged (word stays until the next one)
    POP = 0.14             # seconds of the little "pop" at the start of each word

    def __init__(self, words, accent):
        self.w = words
        self.starts = [x["start"] for x in words]
        self.accent = accent
        self.n = len(words)

    def at(self, t):
        """-> None (nothing shown) or [text, accent, scale] for time t (seconds)."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return None
        w = self.w[i]
        nxt = self.starts[i + 1] if i + 1 < self.n else None
        show_until = nxt if (nxt is not None and nxt - w["end"] <= self.JOIN) else w["end"] + self.HOLD
        if t >= show_until:
            return None
        k = max(0.0, 1.0 - (t - w["start"]) / self.POP)
        return [w["word"], bool(self.accent[i]), round(1.0 + 0.22 * k * k, 2)]


def build(audio_path, words_json, duration):
    """Returns a Captions object, or None when there is nothing to show."""
    if not os.path.exists(audio_path):
        return None
    words = load_words(audio_path, words_json)
    if not words:
        return None
    accent = [False] * len(words)
    try:                                                 # accent = the loudest words of this clip
        import sfx_engine
        sr = sfx_engine.SR
        x = sfx_engine.decode_audio(audio_path, int(duration * sr))
        lv = np.array([np.sqrt(np.mean(x[int(w["start"] * sr):max(int(w["end"] * sr), int(w["start"] * sr) + 1)] ** 2) + 1e-12)
                       for w in words])
        if len(lv) >= 4:
            accent = list(lv >= np.percentile(lv, 75))
    except Exception:
        pass
    return Captions(words, accent)
