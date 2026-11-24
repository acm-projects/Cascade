"""Fan-edit requests read into style actions: which effects, backgrounds, colours, fonts and words the message asks for.
Whether a message is a fan-edit request at all is chat_router's call (backend/editor/chat_router.py)."""
import re

from .advanced_models import StyleEvent, StyleOptions

KIND_PATTERNS = [
    ('color_pop', r'colou?r[ -]?(pop|splash)|colou?r isolat|isolate (the )?(subject|person|colou?r)|(gr[ae]y|black (and|&) white|b&w|desaturat\w*)(scale)? (the )?background'
                  r'|background\b.{0,12}\b(gr[ae]y|black (and|&) white|b&w|desaturat)|keep (him|her|them|the (subject|person|speaker)) in colou?r'),
    ('bg_swap', r'(swap|replace|change|switch)\w* (out )?(the )?background|background (swap|replace|change)|cut ?out|rotoscop|remove (the )?background'),
    ('shape_reveal', r'shape|\bx[- ]?(shape|wipe|reveal)|star (wipe|reveal)|reveal'),
    ('outline', r'outline|\bglow|stroke|sticker'),
    ('glitch', r'glitch|rgb split|chromatic'),
    ('ink', r'\bink\b|silhouette|threshold|posteri[sz]'),
    ('zoom_blur', r'zoom[- ]?blur|radial blur'),
    ('whip', r'\bwhip|motion blur'),
    ('flash', r'\bflash'),
    ('text', r'\btexts?\b|\bwords?\b|typography|\bfonts?\b|kinetic|\btitles?\b'),
]
BACKGROUND_PATTERNS = [
    ('comic', r'comic|pop[- ]art|manga|cartoon|\bpow\b|\bbam\b'), ('halftone', r'halftone|\bdots\b|newsprint'),
    ('speedlines', r'speed ?lines|action lines|anime'), ('neon', r'neon|cyber|synthwave'),
    ('paper', r'paper|sketch|newspaper|notebook'), ('blur', r'blur(red)? background|bokeh'),
]
FONT_HINTS = [('typewriter', r'typewriter|courier|telegram'), ('war', r'stencil|military|army|\bwar\b|ww ?(2|ii)|copperplate'),
              ('grunge', r'grunge|chalk|scratch|messy'), ('script', r'script|handwrit|cursive'),
              ('poster', r'poster|chunky|bold'), ('ancient', r'ancient|medieval|old[- ]?school|vintage'), ('impact', r'impact')]
PRESET = r'fan[ -]?edit|\bamv\b|edit like|like (this|the|that|my) (reference|video|edit|recording)|spider|styli[sz]|velocity|after effects'
CLEAR = r'\b(remove|clear|undo|delete|turn off|get rid of|disable)\b.{0,20}\b(styl\w*|fan edit|cut ?outs?|background effects?|all effects)'
BROLL = r'(other|more|extra|additional|stock|different|new) (clips?|footage|shots|videos)|b[- ]?roll|stock footage'


def broll_query(text):
    if not re.search(BROLL, text):
        return ''
    about = re.search(r'(?:clips?|footage|shots|videos|b[- ]?roll)\s+(?:of|with|showing|about|from)\s+([a-z0-9 \'-]{3,60})', text)
    if not about:
        return '*'
    return re.split(r'\s+(?:edited|with|then|plus)\b|[,.;!]', about.group(1))[0].strip()[:80] or '*'


def parse_request(message, force=False):
    """The style actions a message asks for; None means it names none. force=True (the router already decided this
    is a fan-edit request) never returns None: with nothing specific named it is a full fan edit."""
    text = message.lower()
    if re.search(CLEAR, text):
        return {'type': 'clear'}
    preset = bool(re.search(PRESET, text))
    kinds = [k for k, p in KIND_PATTERNS if re.search(p, text)]
    backgrounds = [b for b, p in BACKGROUND_PATTERNS if re.search(p, text)]
    name = re.search(r'edited by\s+([a-z0-9._\'-]+(?:\s+[a-z0-9._\'-]+){0,2})', message, re.I)
    words = [w.strip() for w in re.findall(r'["“]([^"”]{1,40})["”]', message) if w.strip()][:8]
    stock = broll_query(text)
    if re.search(r'\b(caption|subtitle)s?\b', text) and not preset and not force:
        return None
    if 'text' in kinds and not (preset or words or re.search(r'crazy|wild|kinetic|animated|slam|fancy|insane|epic|cool|big words|\bfonts\b', text)):
        kinds.remove('text')  # "make the text larger" is a caption change, not a kinetic-text effect
    if backgrounds and not kinds and not preset and re.search(r'background|style|look|effect|edit', text):
        kinds = ['bg_swap']
    if not (preset or kinds or name or force):
        return None  # plain "add b-roll of X" stays with the regular B-roll planner
    palette = 'neon' if re.search(r'neon|purple|cyber', text) else 'gold' if re.search(r'\bgold|orange|sepia', text) \
        else 'mono' if re.search(r'black (and|&) white|\bmono|noir|ww ?(2|ii)|world war', text) and 'color_pop' not in kinds else 'spider'
    font = next((f for f, p in FONT_HINTS if re.search(p, text)), 'impact')
    span = re.search(r'(?:from|between)\s*(\d+(?:\.\d+)?)\s*s?\w*\s*(?:to|and|-)\s*(\d+(?:\.\d+)?)', text)
    if span and kinds and not preset:
        a, b = float(span.group(1)), float(span.group(2))
        if b > a:
            events = [StyleEvent(start=a, duration=min(30, b-a), kind=k, background=(backgrounds or ['comic'])[0], font=font,
                                 text=(words[0] if words else '') if k == 'text' else '') for k in kinds[:3]]
            events = [e for e in events if e.kind != 'text' or e.text]
            if events:
                return {'type': 'events', 'palette': palette, 'events': events}
    if preset:
        kinds = [k for k in kinds if k != 'text']  # a full fan edit always includes kinetic text
    intensity = 'subtle' if re.search(r'subtle|light|less|calm|minimal', text) else 'high'
    return {'type': 'preset', 'options': StyleOptions(palette=palette, effects=kinds, backgrounds=backgrounds, intensity=intensity,
                                                      end_card='Cascade', texts=not re.search(r'no (text|words|titles)', text),
                                                      words=words, broll_query=stock)}


def proposal_for(request):
    from .models import Action, Proposal
    if request['type'] == 'clear':
        return Proposal(message='Removed stylized effects.', actions=[Action(type='style_clear')], planning_method='direct_revision')
    if request['type'] == 'events':
        return Proposal(message='Added timed style effects.', actions=[Action(type='style_event', style=e, text=request['palette'])
                        for e in request['events']], planning_method='direct_revision')
    return Proposal(message='Applied a beat-synced fan-edit style with local subject cutouts.',
                    actions=[Action(type='style_preset', style_options=request['options'])], planning_method='direct_revision')
