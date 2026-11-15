import json, re
import sys
P=json.load(open(sys.argv[1] if len(sys.argv)>1 else "edit_plan.json")); W=json.load(open(sys.argv[2] if len(sys.argv)>2 else "transcript.json"))
beats=P["beats"]; issues=[]
TEMPL={"KINETIC_KEYWORD","TEXT_BEHIND_SUBJECT","NUMBER_COUNTER","MAP_CALLOUT","BROLL_OVERLAY","SCREENSHOT_CALLOUT","SCRIBBLE_HIGHLIGHT","COLLAGE","SPEAKER_CUTOUT_ICONS","PLAIN_SPEAKER"}
norm=lambda s: re.sub(r"[^a-z0-9' ]","",s.lower())
def add(r,sev,beat,msg): issues.append((r,sev,beat,msg))

# 1 coverage
w0,w1=P["source_window"]["start"],P["source_window"]["end"]
if abs(beats[0]["start"]-w0)>.01 or abs(beats[-1]["end"]-w1)>.01: add(1,"high",None,"window not fully covered")
for a,b in zip(beats,beats[1:]):
    if abs(a["end"]-b["start"])>.001: add(1,"high",b["id"],f'gap/overlap {a["end"]}->{b["start"]}')
inwin=[w for w in W if w0-1e-6<=w["start"]<w1]
got=sum(len(b["spoken_text"].split()) for b in beats)
if got!=len(inwin): add(1,"high",None,f"words in beats {got} != words in window {len(inwin)}")
# 2 hook
if beats[0]["start"]-w0>3: add(2,"high",1,"hook not in first 3s")
# 3 pacing
lens=[b["end"]-b["start"] for b in beats]
for b,l in zip(beats,lens):
    if l>3.0+1e-6: add(3,"high",b["id"],f"{l:.2f}s > 3.0s")
    if l<0.6: add(3,"medium",b["id"],f"{l:.2f}s < 0.6s")
avg=sum(lens)/len(lens)
if not 1.0<=avg<=2.0: add(3,"medium",None,f"avg beat {avg:.2f}s outside 1.0-2.0")
# 4 variety
for a,b in zip(beats,beats[1:]):
    if a["template"]==b["template"]: add(4,"high",b["id"],"same template back to back")
plains=[b for b in beats if b["template"]=="PLAIN_SPEAKER"]
for a,b in zip(plains,plains[1:]):
    if b["start"]-a["start"]<10: add(4,"medium",b["id"],"PLAIN_SPEAKER twice within 10s")
for b in beats:
    win=[x["template"] for x in beats if b["start"]<=x["start"]<b["start"]+15]
    if (b["start"]+15<=w1) and len(set(win))<4: add(4,"medium",b["id"],f"only {len(set(win))} templates in 15s window")
# 5 fit
for b in beats:
    if re.search(r"\d",b["spoken_text"]) and b["template"]!="NUMBER_COUNTER": add(5,"medium",b["id"],"number spoken, no counter")
# 6 text
for b in beats:
    sw={norm(w) for w in b["spoken_text"].split()}
    for field in ("emphasis_text","accent_word"):
        v=b[field]
        if v:
            toks=norm(v).split()
            if len(toks)>4: add(6,"medium",b["id"],f"{field} > 4 words")
            for t in toks:
                if t not in sw: add(6,"high",b["id"],f"'{t}' in {field} not spoken in this beat")
    if b["template"]!="PLAIN_SPEAKER" and not b["emphasis_text"]: add(6,"high",b["id"],"missing emphasis_text")
# template share cap
from collections import Counter as _C
for t,c in _C(b["template"] for b in beats).items():
    if len(beats)>=12 and c/len(beats)>0.36: add(4,"medium",None,f"{t} is {c}/{len(beats)} beats (>36%)")
# 8 contrast
run=1
for a,b in zip(beats,beats[1:]):
    run=run+1 if a["background_mode"]==b["background_mode"] else 1
    if run>=3: add(8,"medium",b["id"],"3+ same background_mode in a row")
# 9 transitions
for x,y,z in zip(beats,beats[1:],beats[2:]):
    if x["transition_in"]==y["transition_in"]==z["transition_in"]: add(9,"low",y["id"],"same transition 3x")
# 10 broll
for b in beats:
    if b["template"] in("BROLL_OVERLAY","COLLAGE"):
        if not b["broll_query"] or not b["broll_fallback_query"]: add(10,"high",b["id"],"missing b-roll query/fallback")
        elif b["broll_query"]==b["broll_fallback_query"]: add(10,"low",b["id"],"fallback same as query")
# 12 feasibility
for b in beats:
    if b["template"] not in TEMPL: add(12,"high",b["id"],"unknown template")
from collections import Counter
print("beats:",len(beats),"| avg beat: %.2fs"%avg,"| max: %.2fs"%max(lens),"| min: %.2fs"%min(lens))
print("template mix:",dict(Counter(b["template"] for b in beats)))
print("issues:",len(issues))
for i in issues: print("  rule",i[0],i[1],"beat",i[2],"-",i[3])
