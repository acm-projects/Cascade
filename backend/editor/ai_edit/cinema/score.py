"""Original score, sound design and the final mix: composed for each edit, free, made on this machine.

Studied from the INSPO audio (see INSPO_NOTES.md): the nature and save-the-planet references sit on
a dark, low bed (a sub pedal and long felt-piano and pad notes, about 66-80 BPM), real ambience under
everything, and, the main emotional tool, the music drops to SILENCE right before the payoff line and
comes back with a sub hit. No stock "ding / whoosh / boing" pack sounds: every effect here is tuned
to the score's key and kept under the voice.
"""
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
n2f = lambda n: 440*2**((n-69)/12)

# D minor, cinematic: i - VI - III - VII, and a brighter lift for the payoff.
CHORDS = {'Dm': [50, 57, 62, 65, 69], 'Bb': [46, 58, 62, 65, 70], 'F': [41, 57, 60, 65, 69], 'C': [48, 55, 60, 64, 67],
          'Gm': [43, 55, 58, 62, 67], 'Am': [45, 57, 60, 64, 69], 'D': [50, 57, 62, 66, 69]}
MOODS = {
    'awakening': {'bpm': 70, 'build': ['Dm', 'Bb', 'F', 'C'], 'lift': ['Bb', 'F', 'C', 'Dm'], 'pulse': True},
    'wonder': {'bpm': 66, 'build': ['F', 'C', 'Dm', 'Bb'], 'lift': ['Bb', 'C', 'F', 'F'], 'pulse': False},
    'tension': {'bpm': 78, 'build': ['Dm', 'Gm', 'Dm', 'Am'], 'lift': ['Bb', 'C', 'Dm', 'Dm'], 'pulse': True},
    'warm': {'bpm': 72, 'build': ['F', 'Am', 'Bb', 'C'], 'lift': ['F', 'C', 'Bb', 'F'], 'pulse': False},
}


def _lp(f, order=2):
    return butter(order, f, 'lp', fs=SR, output='sos')


def _hp(f, order=2):
    return butter(order, f, 'hp', fs=SR, output='sos')


def _bp(a, b, order=2):
    return butter(order, [a, b], 'bp', fs=SR, output='sos')


def _add(buf, t, x):
    i = int(t*SR)
    if i >= len(buf) or i+len(x) <= 0: return
    if i < 0: x, i = x[-i:], 0
    m = min(len(x), len(buf)-i)
    buf[i:i+m] += x[:m]


def _st(x, pan=0.):
    return np.stack([x*math.cos((pan+1)*math.pi/4), x*math.sin((pan+1)*math.pi/4)], 1)*1.414


def _env(n, attack, release, total=None):
    i = np.arange(n)
    a = np.minimum(i/max(1, attack*SR), 1)
    r = np.minimum((n-i)/max(1, release*SR), 1)
    return (a*r)**1.5


def _reverb(x, seconds=3.2, mix=.35, seed=1, tone=4200):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds*SR))/SR
    ir = np.stack([sosfilt(_lp(tone), rng.standard_normal(len(t)))*np.exp(-t/(seconds/5.5)) for _ in range(2)], 1)
    ir[:int(.012*SR)] *= np.linspace(0, 1, int(.012*SR))[:, None]
    ir /= np.sqrt((ir**2).sum(0)).max()
    wet = np.stack([fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)
    return x*(1-mix)+wet*mix


def _piano(f, d=3.6, velocity=.7, seed=0):
    """A felt piano note: slightly inharmonic partials, faster decay up high, a soft hammer."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(d*SR))/SR
    x = np.zeros_like(t)
    B = .00035
    for k in range(1, 11):
        fk = f*k*math.sqrt(1+B*k*k)
        if fk > 9000: break
        decay = 2.6/(1+.55*(k-1))*(1.25 if f < 200 else 1)
        x += np.sin(2*math.pi*fk*t+rng.uniform(0, 6.28))*(velocity**(1+k*.12))/k**1.15*np.exp(-t/decay)
    hammer = sosfilt(_lp(1800), rng.standard_normal(int(.03*SR)))*np.exp(-np.arange(int(.03*SR))/(.006*SR))*.25
    x[:len(hammer)] += hammer
    x *= np.minimum(t/.004, 1)
    return sosfilt(_lp(3200+2400*velocity), x)


def _pad(notes, d, seed=0, bright=1400):
    """Detuned saw ensemble through a slowly opening filter."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(d*SR))/SR
    left, right = np.zeros_like(t), np.zeros_like(t)
    for n in notes:
        for v in range(5):
            det = (v-2)*.0045
            f = n2f(n)*(1+det)
            ph = rng.uniform(0, 1)
            saw = 2*np.mod(f*t+ph, 1)-1
            (left if v % 2 else right)[:] += saw*.18
            (right if v % 2 else left)[:] += saw*.08
    cut = bright*(1+.35*np.sin(2*math.pi*t/(d*1.7)))
    sos = _lp(float(np.median(cut)))
    out = np.stack([sosfilt(sos, left), sosfilt(sos, right)], 1)
    return out*_env(len(t), min(1.6, d*.4), min(1.4, d*.4))[:, None]


def _sub(f, d):
    t = np.arange(int(d*SR))/SR
    return np.sin(2*math.pi*f*t)*_env(len(t), .8, 1.)


def _thump(f0=58, d=.7, drop=.55):
    t = np.arange(int(d*SR))/SR
    f = f0*(1-drop*(1-np.exp(-t*14)))
    phase = 2*math.pi*np.cumsum(f)/SR
    return np.sin(phase)*np.exp(-t/.16)*np.minimum(t/.002, 1)


def _boom(f0=49, d=2.4):
    """A tuned sub drop, the hit after the silence."""
    t = np.arange(int(d*SR))/SR
    f = f0*(1+1.6*np.exp(-t*9))
    x = np.sin(2*math.pi*np.cumsum(f)/SR)*np.exp(-t/.7)*np.minimum(t/.003, 1)
    crack = sosfilt(_bp(400, 3000), np.random.default_rng(5).standard_normal(len(t)))*np.exp(-t/.05)*.25
    return x+crack


def _air(d=.55, up=True, seed=2):
    """Air moving past: band-passed noise sweeping, for the moments b-roll arrives (no stock swish)."""
    rng = np.random.default_rng(seed)
    n = int(d*SR)
    noise = rng.standard_normal(n)
    t = np.arange(n)/n
    lo = sosfilt(_bp(250, 900), noise); hi = sosfilt(_bp(1500, 5200), noise)
    mix = t if up else 1-t
    x = lo*(1-mix)+hi*mix*.7
    return x*np.sin(np.pi*t)**1.6


def _drop(f=1320, seed=4):
    """A single water drop: a short upward resonant chirp."""
    t = np.arange(int(.18*SR))/SR
    fr = f*(1+.9*(1-np.exp(-t*60)))
    x = np.sin(2*math.pi*np.cumsum(fr)/SR)*np.exp(-t/.03)
    return x*np.minimum(t/.0008, 1)


def _splash(seed=6, d=1.1):
    rng = np.random.default_rng(seed)
    n = int(d*SR)
    t = np.arange(n)/SR
    body = sosfilt(_bp(700, 7000), rng.standard_normal(n))*np.exp(-t/.11)*np.minimum(t/.004, 1)
    x = body.copy()
    for _ in range(18):  # droplets falling back
        at = rng.uniform(.05, .8)
        d0 = _drop(rng.uniform(900, 2400), int(rng.integers(0, 99)))*rng.uniform(.1, .35)
        i = int(at*SR); m = min(len(d0), n-i)
        x[i:i+m] += d0[:m]
    return x


def _rain(n, seed=9, level=1.):
    """Soft rainforest rain: fine filtered noise with slow breathing."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((n, 2))
    x = np.stack([sosfilt(_bp(1800, 9000), noise[:, c]) for c in range(2)], 1)
    t = np.arange(n)/SR
    swell = .75+.25*np.sin(2*math.pi*t/9.3)*np.sin(2*math.pi*t/4.1+1)
    drops = np.zeros(n)
    for at in rng.uniform(0, n/SR, int(n/SR*6)):
        d = _drop(rng.uniform(1600, 3800))*rng.uniform(.05, .2)
        i = int(at*SR); m = min(len(d), n-i); drops[i:i+m] += d[:m]
    return (x*swell[:, None]*.6+_st(sosfilt(_hp(900), drops), 0)*.5)*level


def _level(x, db):
    active = x[np.abs(x).max(1) > 1e-5] if x.ndim == 2 else x[np.abs(x) > 1e-5]
    rms = math.sqrt(float((active**2).mean())) if len(active) else 1
    return x*10**(db/20)/max(rms, 1e-9)


def compose(total, cues, mood='awakening', seed=11):
    """The music bed for `total` seconds.

    cues: {'silence': (a, b) or None, 'end': t of the end stamp, 'hook_end': t}"""
    m = MOODS.get(mood, MOODS['awakening'])
    beat = 60/m['bpm']
    bar = beat*4
    N = int((total+4)*SR)
    pad, piano, sub, pulse = (np.zeros((N, 2)) for _ in range(4))
    silence = cues.get('silence')
    end = cues.get('end', total)
    hook_end = cues.get('hook_end', bar*2)
    lift_at = silence[1] if silence else total*.66
    rng = np.random.default_rng(seed)
    t, k = 0., 0
    while t < end:
        lifted = t >= lift_at-.01
        seq = m['lift'] if lifted else m['build']
        chord = CHORDS[seq[k % 4]]
        length = bar
        if silence and t < silence[0] < t+bar: length = silence[0]-t     # stop dead at the silence
        if silence and silence[0] <= t < silence[1]:
            t, k = silence[1], 0; continue
        if t+length > end: length = end-t
        if length < .3: t += length; k += 1; continue
        _add(pad, t, _pad(chord[1:], length+(0.02 if silence and abs(t+length-silence[0]) < .01 else 1.2), seed+k, 900 if not lifted else 1700))
        _add(sub, t, _st(_sub(n2f(chord[0]-12 if chord[0] >= 48 else chord[0]), length+(.02 if silence and abs(t+length-silence[0]) < .01 else .9))))
        # felt piano: sparse in the hook, a small rising figure in the build, wider after the lift
        steps = [0, 2] if t < hook_end else ([0, 1.5, 2.5, 3] if not lifted else [0, 1, 2, 2.5, 3, 3.5])
        figure = [chord[1]+12, chord[2]+12, chord[3]+12, chord[4]+12, chord[3]+12, chord[2]+24]
        for j, s in enumerate(steps):
            at = t+s*beat
            if at >= t+length-.05: break
            note = figure[(j+k) % len(figure)]
            _add(piano, at, _st(_piano(n2f(note), 3.4, .45 if not lifted else .6, seed+k*7+j), rng.uniform(-.4, .4)))
        if m['pulse'] and hook_end <= t and not lifted:
            q = 0.
            while q < length-.1:
                _add(pulse, t+q, _st(_thump(52, .6)*.9)); _add(pulse, t+q+beat*.32, _st(_thump(46, .5)*.5))
                q += beat*2
        t += length; k += 1
    music = (_level(_reverb(pad, 4., .45, seed), -22)+_level(_reverb(piano, 3.4, .42, seed+1, 5200), -24)
             +_level(sub, -27)+(_level(pulse, -27) if pulse.any() else 0))
    # swell into the silence: a rising filtered noise breath, so the stop is felt
    if silence:
        d = min(3.5, silence[0]-.2)
        if d > .8:
            n = int(d*SR)
            swell = sosfilt(_bp(300, 4000), rng.standard_normal(n))*np.linspace(0, 1, n)**3
            _add(music, silence[0]-d, _level(_st(swell), -30))
        music[int(silence[0]*SR):int(silence[1]*SR)] = 0
    return music[:int(total*SR)]


def sound_design(total, events):
    """events: [(t, kind, tone)] -> stereo effects bed."""
    N = int((total+3)*SR)
    fx = np.zeros((N, 2))
    for t, kind, tone in events:
        if kind == 'broll': _add(fx, t-.32, _level(_st(_air(.6, True, int(t*10))), -33))
        elif kind == 'moment':
            x = _thump(73.4 if tone != 'danger' else 61.7, .9, .4)
            _add(fx, t-.01, _level(_st(x), -27))
            if tone == 'water': _add(fx, t, _level(_st(_drop(), .3), -34))
        elif kind == 'slam': _add(fx, t, _level(_st(_boom(46)), -22))
        elif kind == 'boom': _add(fx, t, _level(_st(_boom(49)), -21))
        elif kind == 'flash': _add(fx, t-.25, _level(_st(_air(.4, True, 77)), -34))
    return fx[:int(total*SR)]


def stamp_audio(d=2.7):
    """The Cascade sting: a drop falls, splashes, a soft major chord blooms."""
    N = int(d*SR)
    x = np.zeros((N, 2))
    _add(x, .05, _level(_st(_drop(1500)), -30))
    _add(x, .42, _level(_st(_drop(1100)), -26))
    _add(x, .48, _level(np.stack([_splash(6), _splash(7)], 1), -26))
    _add(x, .48, _level(_st(_thump(73.4, 1.2, .3)), -28))
    bloom = _reverb(_pad(CHORDS['D'][1:], 2.1, 3, 2200), 3, .5, 4)
    _add(x, .55, _level(bloom, -27))
    for j, n in enumerate([74, 78, 81, 86]):
        _add(x, .7+j*.11, _level(_st(_piano(n2f(n), 1.9, .5, j), (j-1.5)*.3), -33))
    return _reverb(x, 2.2, .25, 8)*np.minimum(1, (N-np.arange(N))/(.4*SR))[:, None]


def measure(path, ffmpeg='ffmpeg'):
    out = subprocess.run([ffmpeg, '-hide_banner', '-nostats', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         capture_output=True, text=True, timeout=300).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', out)[-1]), float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', out)[-1])


def write_wav(path, x):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1)*32767).astype('<i2').tobytes())


def mix(voice, music, fx, ambience_level, out, ffmpeg='ffmpeg', music_under=-17., stamp=None, stamp_at=None):
    """Voice on top; music ducked under speech; ambience and effects beneath; master at -14 LUFS, -1 dB peak."""
    N = len(voice)
    v = voice if voice.ndim == 2 and voice.shape[1] == 2 else np.repeat(voice.reshape(-1, 1), 2, 1)
    v = sosfilt(_hp(85), v, axis=0)
    # how loud the voice is, as a smooth envelope for ducking
    env = np.convolve(np.abs(v).mean(1), np.ones(int(.05*SR))/int(.05*SR), 'same')
    speaking = env > np.percentile(env[env > 1e-6], 25)*1.5 if (env > 1e-6).any() else np.zeros(N, bool)
    hold = np.convolve(speaking.astype(float), np.ones(int(.35*SR)), 'same') > 0
    duck_db = np.where(hold, 0., 7.)
    k = int(.18*SR)
    duck_db = np.convolve(duck_db, np.ones(k)/k, 'same')
    def fit(x):
        x = x[:N] if len(x) >= N else np.concatenate([x, np.zeros((N-len(x), 2))])
        return x
    music, fx = fit(music), fit(fx)
    vr = math.sqrt(float((v[hold]**2).mean())) if hold.any() else .05
    mr = math.sqrt(float((music**2).mean()))+1e-9
    music = music*(vr*10**(music_under/20)/mr)*(10**(duck_db/20))[:, None]
    amb = _rain(N, level=1.)
    amb = amb*(vr*10**((music_under-11+ambience_level)/20)/(math.sqrt(float((amb**2).mean()))+1e-9))
    fxr = fx*(vr/.1)
    total = v+music+amb+fxr
    if stamp is not None and stamp_at is not None:
        _add(total, stamp_at, stamp*(vr/.1)*1.2)
    folder = Path(out).parent
    pre = folder/'_premix.wav'
    write_wav(pre, total/(np.abs(total).max()+1e-9)*.5)
    # two-pass loudness to -14 LUFS with a true-peak ceiling
    first = subprocess.run([ffmpeg, '-hide_banner', '-nostats', '-i', str(pre), '-af', 'loudnorm=I=-14:TP=-1.2:LRA=11:print_format=json', '-f', 'null', '-'],
                           capture_output=True, text=True, timeout=300).stderr
    stats = re.search(r'\{[^{}]*"input_i"[^{}]*\}', first, re.S)
    import json
    s = json.loads(stats.group(0)) if stats else None
    filt = 'loudnorm=I=-14:TP=-1.2:LRA=11' + (f":measured_I={s['input_i']}:measured_TP={s['input_tp']}:measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}:offset={s['target_offset']}:linear=true" if s else '')
    run = subprocess.run([ffmpeg, '-nostdin', '-y', '-v', 'error', '-i', str(pre), '-af', filt+',alimiter=limit=0.89:level=disabled', '-ar', str(SR), '-c:a', 'pcm_s16le', str(out)],
                         capture_output=True, text=True, timeout=300)
    pre.unlink(missing_ok=True)
    if run.returncode: raise ValueError('I could not mix the audio for this edit.')
    return measure(out, ffmpeg)
