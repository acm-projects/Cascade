"""Voice first, then an original track composed to fit it, on the same beat grid. Free and local."""
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from . import tools

SR = 48000
CHORDS = {'Am': [45, 57, 60, 64], 'F': [41, 57, 60, 65], 'Dm': [38, 57, 62, 65], 'E': [40, 56, 59, 64], 'C': [36, 55, 60, 64], 'G': [43, 55, 59, 62]}
HOME, DARK, OPEN = ['Am', 'F', 'C', 'G'], ['Am', 'F', 'Dm', 'E'], ['C', 'G', 'Am', 'F']
n2f = lambda n: 440*2**((n-69)/12)


def measure(path):
    out = subprocess.run([tools.ffmpeg(), '-hide_banner', '-nostats', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True, timeout=300).stderr
    return (float(re.findall(r'I:\s+(-?[\d.]+) LUFS', out)[-1]), float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', out)[-1]), float(re.findall(r'LRA:\s+(-?[\d.]+) LU', out)[-1]))


def _write(path, x):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1)*32767).astype('<i2').tobytes())


def _tone(f, d, harm=8, roll=1.6, det=0, ph=0):
    t = np.arange(int(d*SR))/SR
    return sum(np.sin(2*np.pi*f*(1+det)*h*t+ph*h)/h**roll for h in range(1, harm+1) if f*h <= 7000)


def _add(buffer, t, x):
    i = int(t*SR)
    if i >= len(buffer): return
    m = min(len(x), len(buffer)-i)
    buffer[i:i+m] += x[:m]


def _st(x, p=.5):
    return np.stack([x*(1-p)*2**.5, x*p*2**.5], 1)


def _sections(plan, layout):
    """(start beat, end beat, chords, style) of music, stopping for the silence and the verdict."""
    beat = layout.beat
    total = layout.total/beat
    stop = (layout.closing[1]/beat if layout.closing else layout.silence[0]/beat) if layout.silence else None
    back = layout.reset[1]/beat if layout.reset else None
    earth = plan.mode == 'earth'
    def style(part):
        if earth: return {'home': (HOME, 'soft'), 'loss': (DARK, 'pulse'), 'cost': (DARK, 'pulse'), 'left': (OPEN, 'open'), 'main': (DARK, 'pulse')}[part]
        return {'dark': (DARK, 'pulse'), 'warm': (OPEN, 'open'), 'driving': (DARK, 'drive')}.get(plan.mood, (DARK, 'pulse'))
    groups, start = [], 0
    for one, two in zip(layout.lines, [*layout.lines[1:], None]):
        change = two and style(two['plan'].part) != style(one['plan'].part)
        if change or not two:
            at = round(two['t']/beat) if two else total
            groups.append((start, at, *style(one['plan'].part))); start = at
    out = []
    for a, z, chords, kind in groups:
        if stop is not None and a < stop: out.append((a, min(z, stop), chords, kind, min(z, stop) == stop and z > stop))
        if back is not None and z > back: out.append((max(a, back), z, chords, kind, False))
        if stop is None: out.append((a, z, chords, kind, False))
    return [s for s in out if s[1] > s[0]]


def _compose(plan, layout, N, rng):
    b = layout.b
    buf = lambda: np.zeros((N+SR*4, 2))
    pad, sub, pulse, bell = buf(), buf(), buf(), buf()
    for s, e, seq, kind, hard in _sections(plan, layout):
        bars = max(1, math.ceil((e-s)/4-1e-6))
        for bar in range(bars):  # counted in whole bars: a float remainder must never stall this
            bt = s+bar*4
            nb = min(bt+4, e); end = hard and bar == bars-1
            if nb-bt < .01: continue
            d = (nb-bt)*layout.beat+(.02 if end else 1.2)
            c = CHORDS[seq[bar % 4]]
            i = np.arange(int(d*SR))
            env = np.minimum(i/(.5*SR), 1)*np.minimum((len(i)-i)/((.02 if end else 1.)*SR), 1)
            L = sum(_tone(n2f(n), d, 10, 1.5, -.0016, .3) for n in c[1:])*env
            R = sum(_tone(n2f(n), d, 10, 1.5, .0016, 1.1) for n in c[1:])*env
            _add(pad, b(bt), np.stack([L, R], 1))
            root = c[0]
            while root >= 40: root -= 12
            q, step = bt, (4 if kind == 'soft' else 1 if kind == 'drive' else 2)
            while q < nb-.01:
                ii = np.arange(SR); ev = np.exp(-ii/(.36*SR))*np.minimum(ii/(.012*SR), 1)
                _add(sub, b(q), _st(_tone(n2f(root+12), 1, 3, 2.2)*ev)); q += step
            if kind in ('pulse', 'drive', 'open'):
                q = bt
                while q < nb-.01:
                    ii = np.arange(int(.3*SR)); ev = np.exp(-ii/(.08*SR))*np.minimum(ii/(.004*SR), 1)
                    _add(pulse, b(q), _st(_tone(n2f(root+24), .3, 5, 1.8)*ev*(1 if abs(q % 1) < .01 else .65))); q += .5
            if kind == 'open':
                notes, q, j = sorted(c[1:]), bt, 0
                while q < nb-.01:
                    t = np.arange(int(1.3*SR))/SR; nn = notes[[0, 2, 1, 2][j % 4]]+12
                    x = (np.sin(2*np.pi*n2f(nn)*t)+.2*np.sin(4*np.pi*n2f(nn)*t))*np.exp(-t/.36)*np.minimum(t/.003, 1)
                    _add(bell, b(q), _st(x, .5+.25*np.sin(j*1.3))); q += 1; j += 1
    sos = butter(2, 2800, 'lp', fs=SR, output='sos'); irt = np.arange(int(2.2*SR))/SR
    ir = np.stack([sosfilt(sos, rng.standard_normal(len(irt)))*np.exp(-irt/.5) for _ in range(2)], 1); ir /= np.sqrt((ir**2).sum(0)).max()
    verb = lambda x, m: x*(1-m)+np.stack([fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)*m
    rms = lambda x: np.sqrt((x**2).mean())+1e-9
    def lvl(x, db):
        active = x[x.any(1)]
        return x*10**(db/20)/rms(active) if len(active) else x
    lp = butter(2, 3000, 'lp', fs=SR, output='sos'); hp = butter(2, 140, 'hp', fs=SR, output='sos')
    return (lvl(verb(sosfilt(lp, sosfilt(hp, pad, axis=0), axis=0), .3), -22)+lvl(sub, -26)+lvl(verb(sosfilt(lp, pulse, axis=0), .2), -30)+lvl(verb(bell, .45), -30))[:N]


def _user_track(path, N, first_beat):
    raw = subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-i', str(path), '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, timeout=300).stdout
    x = np.frombuffer(raw, '<f4').reshape(-1, 2)[int(first_beat*SR):]
    return np.resize(x, (N, 2)).copy() if len(x) else np.zeros((N, 2))


def mix(plan, layout, prep_dir, prep, dots, out, track=None):
    """Writes the master; returns the numbers the owner's sheet asks to report."""
    N, rng = int(layout.total*SR), np.random.default_rng(11)
    ti = np.arange(N)/SR
    beat, b = layout.beat, layout.b
    # voice, line by line, at an even level across speakers
    raw = subprocess.run([tools.ffmpeg(), '-nostdin', '-v', 'error', '-i', str(Path(prep_dir)/prep['voice']), '-af', 'highpass=f=90,acompressor=threshold=-24dB:ratio=2.5:attack=8:release=120,equalizer=f=3000:t=q:w=1.2:g=2',
                          '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, timeout=600).stdout
    raw = np.frombuffer(raw, '<f4'); V = np.zeros(N+SR)
    for line in layout.lines:
        chosen = line['plan']
        a, z = line['a'], line['a']+line['end']-line['t']
        x = raw[int(a*SR):int((z+.02)*SR)].copy(); fd = min(int(.02*SR), len(x)//2)
        if fd:
            x[:fd] *= np.linspace(0, 1, fd); x[-fd:] *= np.linspace(1, 0, fd)
        voiced = x[np.abs(x) > 1e-3]
        x = x*10**(-20/20)/max(np.sqrt((voiced**2).mean()) if len(voiced) else 1, 1e-6)
        _add(V[:, None], line['t'], x[:, None])
    V = V[:N]; VS = _st(V)
    # music
    if plan.mood == 'none' and track is None: music = np.zeros((N, 2))
    elif track is not None: music = _user_track(track[0], N, track[1])
    else: music = _compose(plan, layout, N, rng)
    gate = np.ones(N)
    if layout.silence:
        off = layout.closing[1] if layout.closing else layout.silence[0]
        on = layout.reset[1] if layout.reset else layout.end_card
        gate = ((ti < off) | (ti >= on)).astype(float)
    earth = plan.mode == 'earth'
    beats = ti/beat
    # builds toward the verdict, opens quieter after it, lifts on the end card
    stop = (layout.closing[1] if layout.closing else layout.silence[0])/beat if layout.silence else layout.end_card/beat
    points = [(0, -6 if earth else -3), (stop*.5, -2), (stop, 2)]
    if layout.reset: points += [(layout.reset[1]/beat, -5), ((layout.reset[1]+layout.end_card)/2/beat, -2)]
    points += [(layout.end_card/beat, 0), (layout.end_card/beat+1, 5), (layout.total/beat, 5)]
    shape = np.interp(beats, [p[0] for p in points], [p[1] for p in points])
    fade = np.clip((layout.total-ti)/1.6, 0, 1)**1.3
    music = music*(gate*10**(shape/20)*fade)[:, None]
    # effects, all on beats, low hits below the voice
    sf = np.zeros((N+SR*2, 2)); effects = []
    def fx(t, x, db):
        _add(sf, t, x*10**(db/20)/np.abs(x).max()); effects.append(t)
    def hit(f0=55, d=1.2, tau=.3):
        t = np.arange(int(d*SR))/SR
        return _st(np.sin(2*np.pi*(f0*t+(f0*.8/18)*(1-np.exp(-18*t))))*np.exp(-t/tau)*np.minimum(t/.003, 1))
    def glint():
        t = np.arange(int(1.4*SR))/SR
        return _st(sum(a*np.sin(2*np.pi*f*t)*np.exp(-t/dc) for a, f, dc in [(1, 1046.5, .5), (.6, 1318.5, .38), (.4, 1568, .28)])*np.minimum(t/.002, 1))
    def tick():
        t = np.arange(int(.12*SR))/SR
        return _st(np.sin(2*np.pi*880*t)*np.exp(-t/.018)*np.minimum(t/.001, 1))
    for flip in layout.part_flips: fx(flip, hit(), -16)
    if layout.closing:
        d = layout.closing[0]-b(round(layout.closing[0]/beat)-3)
        x = sosfilt(butter(2, 1400, 'lp', fs=SR, output='sos'), rng.standard_normal(int(max(d, .5)*SR)))*(np.arange(int(max(d, .5)*SR))/int(max(d, .5)*SR))**2.6
        _add(sf, layout.closing[0]-max(d, .5), _st(x)*10**(-30/20)/(np.sqrt((x**2).mean())+1e-9))
        fx(layout.closing[0], hit(49), -18)
    if layout.silence: fx(layout.silence[0], hit(41, 1.6, .5), -14)
    if layout.reset: fx(b(round(layout.reset[1]/beat)), glint(), -26)
    fx(layout.end_card, hit(55, 1.4, .4), -22); fx(layout.end_card, glint(), -28)
    onsets = [t for line in layout.lines for _, t, _ in line['words']]
    last = -9
    for dot in sorted(dots):
        if dot-last < 2.4 or (layout.silence and layout.silence[0] <= dot < (layout.reset[1] if layout.reset else layout.end_card)): continue
        if abs(dot/beat-round(dot/beat))*beat > 2/30 or min(abs(s-dot) for s in onsets) < .1: continue
        fx(dot, tick(), -33); last = dot
    sf = sf[:N]
    x = rng.standard_normal((N, 2))
    air = sosfilt(butter(2, [60, 500], 'bp', fs=SR, output='sos'), x, axis=0); air = air*10**(-46/20)/np.sqrt((air**2).mean())
    # the music sits at the level the plan asks for, against the voice
    folder = Path(out).parent
    mask = np.convolve(np.abs(V) > 1e-3, np.ones(int(.3*SR))/int(.3*SR), 'same') > .02
    keep = np.where(mask & (gate > 0))[0]
    achieved = None
    if music.any() and len(keep) > SR:
        _write(folder/'_v.wav', VS); _write(folder/'_m.wav', music[keep])
        lv, lm = measure(folder/'_v.wav')[0], measure(folder/'_m.wav')[0]
        music *= 10**((lv+plan.music_db-lm)/20)
        _write(folder/'_m.wav', music[keep]); achieved = round(measure(folder/'_m.wav')[0]-lv, 1)
    duck = 10**(-2.5*np.convolve(mask, np.ones(int(.25*SR))/int(.25*SR), 'same')/20)
    ride = np.interp(beats, [p[0] for p in points[:3]]+[layout.total/beat], [-3 if earth else -1, 0, 1.5, 0]) if not layout.reset else \
        np.interp(beats, [0, stop*.5, stop, layout.reset[1]/beat-.01, layout.reset[1]/beat, layout.end_card/beat, layout.total/beat], [-5.5 if earth else -2, 0, 1.5, 0, -5 if earth else -2, -2, -2])
    total = (VS+music*duck[:, None]+sf+air)*(10**(ride/20))[:, None]
    _write(folder/'_pre.wav', total/4)
    gain, result = 0, None
    for _ in range(6):
        run = subprocess.run([tools.ffmpeg(), '-nostdin', '-y', '-v', 'error', '-i', str(folder/'_pre.wav'), '-af', f'volume={12+gain:.2f}dB,alimiter=limit=0.82:attack=4:release=60:level=disabled', '-ar', str(SR), '-c:a', 'pcm_s16le', str(out)], capture_output=True, text=True, timeout=300)
        if run.returncode: raise ValueError('I could not mix the audio for this edit.')
        result = measure(out)
        if abs(result[0]+14) < .15: break
        gain += -14-result[0]
    for name in ('_v.wav', '_m.wav', '_pre.wav'): (folder/name).unlink(missing_ok=True)
    grid = lambda t: abs(t/beat-round(t/beat))*beat <= 2/30
    return {'lufs': result[0], 'peak': result[1], 'lra': result[2], 'music_vs_voice': achieved,
            'effects': len(effects), 'effects_on_beat': sum(grid(t) for t in effects), 'dots': len(dots), 'dots_on_beat': sum(grid(t) for t in dots)}
