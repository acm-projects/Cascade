"""A dramatic, serious music bed for a beat edit, synthesized here (nothing to license).

    dramatic(total, hits=(), seed=3) -> stereo float array at 48 kHz, `total` seconds long

D minor at 84 bpm: a low string drone and a cello-like pad moving Dm - Bb - Gm - A, a staccato low-string
ostinato that grows through the clip, a slow ticking pulse, taiko-like drums on the bar, a big drum on each `hit`
(the plan's impact moments), and a thin high string line in the second half.
"""
import math

import numpy as np
from scipy.signal import sosfilt

from ..cinema import score

SR = score.SR
BPM = 84
PROGRESSION = [(38, 45, 50, 53), (34, 41, 46, 50), (31, 38, 43, 46), (33, 40, 45, 49)]   # Dm, Bb, Gm, A (MIDI, low)


def _saw(f, n, seed=0, voices=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n)/SR
    return sum(2*np.mod(f*(1+(v-1)*.004)*t+rng.uniform(0, 1), 1)-1 for v in range(voices))/voices


def _string_hit(f, d=.2, seed=0):
    """One staccato low-string note: a detuned saw through a closing filter."""
    n = int(d*SR)
    t = np.arange(n)/SR
    x = sosfilt(score._lp(900), _saw(f, n, seed))
    return x*np.minimum(t/.008, 1)*np.exp(-t/(d*.45))


def _taiko(f=62, d=1.1, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(d*SR))/SR
    skin = score._thump(f, d, .5)
    body = sosfilt(score._bp(80, 700), rng.standard_normal(len(t)))*np.exp(-t/.06)*.5
    return (skin+body)*np.minimum(t/.002, 1)


def _tick(seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(.05*SR))/SR
    return sosfilt(score._bp(2500, 7000), rng.standard_normal(len(t)))*np.exp(-t/.008)


def _high_line(d, f):
    t = np.arange(int(d*SR))/SR
    vib = 1+.004*np.sin(2*math.pi*5.2*t)
    x = np.sin(2*math.pi*np.cumsum(np.full(len(t), f)*vib)/SR)+.3*np.sin(2*math.pi*np.cumsum(np.full(len(t), 2*f)*vib)/SR)
    return x*score._env(len(t), min(2., d*.4), min(1.5, d*.4))


def dramatic(total, hits=(), seed=3):
    beat = 60/BPM
    bar = beat*4
    N = int((total+4)*SR)
    drone, pad, ost, drums, ticks, high = (np.zeros((N, 2)) for _ in range(6))
    rng = np.random.default_rng(seed)
    t, k = 0., 0
    while t < total:
        chord = PROGRESSION[(k//2) % 4]        # each chord lasts two bars
        length = min(bar, total-t)
        if length < .05: break
        grow = min(1., t/max(total*.8, 1))     # 0 at the start, 1 near the end
        score._add(drone, t, score._st(score._sub(score.n2f(chord[0]-12), length+1.)))
        score._add(pad, t, score._pad(chord[1:], length+1.2, seed+k, 520+500*grow))
        # ostinato: root/fifth in eighths, sparse first, every eighth later
        pattern = [0, 3, 4, 7] if grow < .35 else list(range(8))
        for j in pattern:
            at = t+j*beat/2
            if at >= t+length: break
            note = chord[0]+12 if j % 4 != 3 else chord[1]+12
            score._add(ost, at, score._st(_string_hit(score.n2f(note), .22, k*8+j)*(.7+.3*(j % 2 == 0)), rng.uniform(-.3, .3)))
        for j in range(8):
            at = t+j*beat/2
            if at < t+length: score._add(ticks, at, score._st(_tick(k*8+j)*(1 if j % 2 == 0 else .55), .35))
        score._add(drums, t, score._st(_taiko(60, 1.2, k)))
        if grow > .3: score._add(drums, t+beat*2.5, score._st(_taiko(68, .8, k+50)*.6))
        if t >= total*.5:
            score._add(high, t, score._st(_high_line(length+.6, score.n2f(chord[1]+36)), -.2))
        t += bar; k += 1
    for at in hits:
        score._add(drums, max(0., at-.01), score._st(_taiko(52, 1.6, int(at*10))*1.6))
        score._add(drums, max(0., at), score._st(score._boom(44, 1.8)*.5))
    crescendo = (.55+.45*np.minimum(1, np.arange(N)/SR/max(total, 1)))[:, None]
    music = (score._level(score._reverb(drone, 2.5, .3, seed), -26)
             + score._level(score._reverb(pad, 3.6, .45, seed+1, 2600), -24)
             + score._level(score._reverb(ost, 1.6, .25, seed+2, 3000), -25)*crescendo
             + score._level(score._reverb(drums, 2.2, .3, seed+3, 2400), -21)
             + score._level(ticks, -36)*crescendo
             + (score._level(score._reverb(high, 3., .5, seed+4, 5000), -34) if high.any() else 0))
    out = music[:int(total*SR)]
    fade = min(len(out), int(.25*SR))
    if fade: out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out
