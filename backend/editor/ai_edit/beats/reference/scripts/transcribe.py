import json, wave, numpy as np, sherpa_onnx
d = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx",
    joiner=f"{d}/joiner.int8.onnx", tokens=f"{d}/tokens.txt",
    num_threads=4, model_type="nemo_transducer", decoding_method="greedy_search")

w = wave.open("audio.wav"); sr = w.getframerate()
x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768
dur = len(x)/sr

# choose chunk boundaries at the quietest 100ms near every ~25s
hop = int(0.1*sr)
energy = np.array([np.sqrt(np.mean(x[i:i+hop]**2)) for i in range(0, len(x)-hop, hop)])
bounds=[0.0]; t=25.0
while t < dur-8:
    lo, hi = int((t-3)/0.1), int((t+3)/0.1)
    k = lo + int(np.argmin(energy[lo:hi])); bounds.append(k*0.1); t = k*0.1 + 25.0
bounds.append(dur)

words=[]
for a,b in zip(bounds[:-1], bounds[1:]):
    seg = x[int(a*sr):int(b*sr)]
    s = rec.create_stream(); s.accept_waveform(sr, seg); rec.decode_stream(s)
    r = s.result
    cur=None
    for tok, ts in zip(r.tokens, r.timestamps):
        if tok.startswith("▁") or tok.startswith(" ") or cur is None:
            if cur: words.append(cur)
            cur={"word":tok.lstrip("▁ "), "start":round(a+ts,2)}
        else:
            cur["word"]+=tok
    if cur: words.append(cur)
# set end times = next word's start (capped)
for i,wd in enumerate(words):
    nxt = words[i+1]["start"] if i+1<len(words) else dur
    wd["end"] = round(min(nxt, wd["start"]+0.6),2)
json.dump(words, open("transcript.json","w"), indent=1)
print("duration",round(dur,1),"chunks",len(bounds)-1,"words",len(words))
