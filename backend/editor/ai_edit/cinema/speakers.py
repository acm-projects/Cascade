"""Who is talking. Podcasts and Q&A clips have one person asking and one answering; the answer
should play without the other person's "yeah", "right" or a quip cutting across it.

Voices are told apart by enrolment: the asking voice is learned from the question itself
(the hook the plan names), the answering voice from the longest stretch of the answer, and every
short turn is scored against both. A turn is only called the other voice when the evidence is
clear, so a real answer is never thrown away by mistake. Claude's plan also names interjections
by reading the transcript; this is the safety net when it misses one."""
import numpy as np


def _mfcc(x, sr, n=20):
    frame, hop = int(.025*sr), int(.010*sr)
    if len(x) < frame: return np.zeros((0, n))
    count = 1+(len(x)-frame)//hop
    idx = np.arange(frame)[None, :]+hop*np.arange(count)[:, None]
    frames = x[idx]*np.hamming(frame)
    nfft = 512
    power = np.abs(np.fft.rfft(frames, nfft))**2/nfft
    mel = lambda f: 2595*np.log10(1+f/700)
    inv = lambda m: 700*(10**(m/2595)-1)
    points = inv(np.linspace(mel(80), mel(min(7600, sr/2)), 26+2))
    bins = np.floor((nfft+1)*points/sr).astype(int)
    bank = np.zeros((26, nfft//2+1))
    for j in range(26):
        a, b, c = bins[j], bins[j+1], bins[j+2]
        if b > a: bank[j, a:b] = (np.arange(a, b)-a)/(b-a)
        if c > b: bank[j, b:c] = (c-np.arange(b, c))/(c-b)
    energy = np.log(power@bank.T+1e-10)
    k = np.arange(26)
    dct = np.cos(np.pi/26*(k[None, :]+.5)*np.arange(n)[:, None])
    return energy@dct.T


def utterances(words, gap=.2):
    """Runs of word indices spoken without a pause, also split after a sentence ends."""
    out, run = [], []
    for i, w in enumerate(words):
        if run and (w['s']-words[run[-1]]['e'] > gap or words[run[-1]]['w'].rstrip().endswith(('?', '.', '!'))):
            out.append(run); run = []
        run.append(i)
    if run: out.append(run)
    return out


class Voices:
    def __init__(self, mono, sr):
        self.m = _mfcc(mono, sr)
        loud = self.m[:, 0] > np.percentile(self.m[:, 0], 40)
        self.mu = self.m[loud, 1:].mean(0)
        self.sd = self.m[loud, 1:].std(0)+1e-6
        self.floor = np.percentile(self.m[:, 0], 40)

    def frames(self, a, b):
        s = self.m[int(a*100):int(b*100)]
        s = s[s[:, 0] > self.floor]
        return (s[:, 1:]-self.mu)/self.sd

    def model(self, spans):
        x = np.concatenate([self.frames(a, b) for a, b in spans] or [np.zeros((0, self.m.shape[1]-1))])
        return (x.mean(0), x.var(0)+.05) if len(x) > 50 else None

    def score(self, a, b, one, two):
        """Mean per-frame log-likelihood ratio of voice `one` over voice `two`."""
        x = self.frames(a, b)
        if len(x) < 15: return 0.
        ll = lambda m: -.5*(((x-m[0])**2)/m[1]+np.log(m[1])).sum(1)
        return float(np.median(ll(one)-ll(two)))


def interjections(words, mono, sr, question, answers, margin=1.6, max_words=14, max_seconds=4.5):
    """Word indices of short turns inside the answers spoken in the asker's voice.

    `question` is (from_word, to_word) of the asker's line; `answers` are (from_word, to_word) spans."""
    if not question or not answers: return set()
    voices = Voices(mono, sr)
    q = (words[question[0]]['s'], words[question[1]]['e'])
    longest = max(answers, key=lambda s: words[s[1]]['e']-words[s[0]]['s'])
    a_span = (words[longest[0]]['s'], words[longest[1]]['e'])
    asker, answerer = voices.model([q]), voices.model([a_span])
    if asker is None or answerer is None: return set()
    out = set()
    for g in utterances(words):
        if not any(first <= g[0] and g[-1] <= last for first, last in answers): continue
        a, b = words[g[0]]['s'], words[g[-1]]['e']
        if len(g) > max_words or b-a > max_seconds: continue
        if voices.score(a, b, asker, answerer) > margin: out.update(g)
    return out
