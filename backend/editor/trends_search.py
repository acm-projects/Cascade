"""Finding YouTube references for a clip: pasted links, search queries, the clip's own keywords and how well a
found video matches. Used by trends.py."""
import re

from fastapi import HTTPException


YOUTUBE_ID=re.compile(r'(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/))([A-Za-z0-9_-]{11})')
def reference_ids(links):
    """YouTube ids from links the user pasted. Anything else is rejected with a clear message."""
    ids=[]
    for link in links:
        link=link.strip()
        match=YOUTUBE_ID.search(link) or (re.fullmatch(r'[A-Za-z0-9_-]{11}',link) and re.match(r'(.*)',link))
        if not match:raise HTTPException(422,'Only YouTube links can be added as references right now.')
        vid=match.group(1)
        if vid not in ids:ids.append(vid)
    return ids

def views_per_hour(video):
    """Views per hour since upload: the ranking proxy for "trending right now". None when YouTube gave no date."""
    from datetime import datetime,timezone
    try:
        published=datetime.fromisoformat(str(video.get('published_at') or '').replace('Z','+00:00'))
        if published.tzinfo is None:published=published.replace(tzinfo=timezone.utc)
        hours=max((datetime.now(timezone.utc)-published).total_seconds()/3600,1.0)
        return round(int(video.get('view_count') or 0)/hours,1)
    except (ValueError,TypeError):return None

def measured(path):
    """FFmpeg measurements (cuts, loudness, size). Never fails research: missing data is shown as unavailable."""
    try:
        from backend.trends.measure import measure_video
        return measure_video(path)
    except Exception:return {}

# What the person picks in the Topic menu -> real YouTube Shorts searches for that kind of video.
CATEGORIES={
    'podcast / interview':['podcast clip','podcast interview moment','podcast highlights'],
    'travel vlog':['travel vlog','travel reel cinematic','travel shorts'],
    'comedy / skit':['funny skit','comedy shorts','funny reaction clip'],
    'talking head / explainer':['talking head explainer','educational shorts','storytime shorts'],
    'food / cooking':['cooking shorts','food recipe reel','restaurant food review'],
    'fitness / lifestyle':['workout shorts','fitness motivation','day in my life'],
    'gaming':['gaming highlights','gaming clip','gaming funny moments'],
    'tech / product review':['tech review shorts','gadget review','product unboxing'],
}

def search_queries(topic):
    """Searches to run for a topic: the curated ones for a menu choice, otherwise what the person typed."""
    known=CATEGORIES.get(topic.strip().lower())
    if known:return list(known)
    topic=topic.strip()
    return [topic,topic+' viral'] if topic else ['viral shorts']

# The main word for each menu choice, combined with the clip's own subject for a more specific search
CATEGORY_NOUN={'podcast / interview':'podcast','travel vlog':'travel vlog','comedy / skit':'comedy','talking head / explainer':'explained',
    'food / cooking':'cooking','fitness / lifestyle':'fitness','gaming':'gaming','tech / product review':'tech review'}
FILLER=set("""the and this that with have your from just what there they them then than were been will would could should about because
really think know like going want people thing things very much some more into over also when where which while their here these those said
says saying gonna wanna yeah okay right well even only make made being doing does dont didnt cant wont youre thats theyre whats were ive
something anything everything actually literally kind sort maybe always never every other another still where shorts clip viral moment reel
video videos time back come came take took give gave look looking need talk talking tell said whether able great quote wanna"""
    .split())

def clip_keywords(clip,info,limit=4):
    """The words that say what this clip is about: its title counts most, then the most repeated words it says."""
    from collections import Counter
    # subject words only: no filler, no contractions (we're, it's), no -ing verbs (saying, passing)
    words=lambda text:[w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{3,}(?!')",text)
                       if w.lower() not in FILLER and not w.lower().endswith('ing') and "'" not in w]
    counts=Counter(words(' '.join(c['text'] for c in info['cues'][:60])))
    for w in words(clip.get('title','')):counts[w]+=5
    return [w for w,n in counts.most_common(limit) if n>1 or w in words(clip.get('title',''))]

def relevance(video,terms):
    """How many of the given words a found video mentions (title, tags, description)."""
    text=' '.join([video.get('title',''),' '.join(video.get('tags') or []),video.get('description','')]).lower()
    return sum(1 for term in terms if re.search(r'\b'+re.escape(term),text))

def match_tier(video,subject,kind):
    """2 = about this clip's subject AND this type of video, 1 = one of the two, 0 = unrelated."""
    return bool(relevance(video,subject))+bool(relevance(video,kind))

def derive_search(clip,info,goal='',override='',tags=None):
    instruction=bool(re.search(r'tell me|improve (?:this|my)|based on trends|make this|help me|research this',override,re.I))
    topic='' if instruction else override.strip()
    if not topic:
        context=' '.join([clip.get('title',''),' '.join(c['text'] for c in info['cues'][:12])]).lower()
        rules=[('travel vlog',r'travel|trip|vlog|flight|hotel|beach|hike|city tour'),('food / cooking',r'recipe|cook|food|restaurant|eat|taste'),
               ('gaming',r'game|gaming|stream|level|boss'),('fitness / lifestyle',r'workout|gym|fitness|routine'),
               ('comedy / skit',r'teddy|bear|comedy|humor|funny|skit|prank'),('tech / product review',r'review|unbox|phone|laptop|gadget')]
        topic=next((name for name,pattern in rules if re.search(pattern,context)),'')
        if not topic:topic='podcast / interview' if info['cues'] else 'travel vlog'
    return topic[:160]

def speech_evidence(info):
    if info.get('cues'):return {'status':'timestamped_transcript','message':'Speech timestamps are available for this clip.','cue_count':len(info['cues'])}
    if not info.get('has_audio'):return {'status':'no_audio_stream','message':'This clip has no audio stream.','cue_count':0}
    return {'status':'unknown','message':'Audio exists, but saved speech timestamps are missing. This does not establish that the clip is dialogue-free.','cue_count':0}
