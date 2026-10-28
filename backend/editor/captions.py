"""Editor captions; extracted without changing media behavior."""
import base64
import io
from fastapi import HTTPException


def caption_intervals(cues, state):
    if not state.captions.enabled:
        return []
    boundaries = sorted({state.start, state.end, *(max(state.start,min(state.end,t)) for c in cues for t in (c['start'],c['end']))})
    intervals = []
    for start,end in zip(boundaries,boundaries[1:]):
        mid=(start+end)/2
        text='\n'.join(state.texts.get(str(i),c['text']) for i,c in enumerate(cues) if c['start']<=mid<c['end'])
        if text:
            intervals.append({'start':start-state.start,'end':end-state.start,'text':text})
    return intervals


def raster_filters(folder, overlays, cues, state, width, height, base_filter="null"):
    """Use the live preview's caption pixels, with validated images/timings only."""
    from PIL import Image
    expected=caption_intervals(cues,state)
    if len(overlays)!=len(expected) or sum(len(o.png) for o in overlays)>40_000_000:
        raise HTTPException(422, 'Caption preview data is outdated or too large. Reload and retry export.')
    if not overlays:
        return [], ['-vf',base_filter]
    Image.new('RGBA',(width,height)).save(folder/'blank.png')
    entries=[]
    def entry(name,duration):
        if duration>0:
            entries.append(f"file '{name}'\noption framerate 1000\nduration {duration:.6f}\n")
    previous=0
    for index,(overlay,interval) in enumerate(zip(overlays,expected)):
        if abs(overlay.start-interval['start'])>.001 or abs(overlay.end-interval['end'])>.001:
            raise HTTPException(422, 'Caption preview timings are outdated. Retry export.')
        try:
            raw=base64.b64decode(overlay.png,validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format!='PNG' or image.size!=(width,height):
                    raise ValueError('Invalid preview size')
                image.verify()
        except (ValueError,OSError,Image.DecompressionBombError):
            raise HTTPException(422, 'Caption preview image is invalid. Retry export.')
        filename=f'overlay_{index}.png'; (folder/filename).write_bytes(raw)
        entry('blank.png',overlay.start-previous); entry(filename,overlay.end-overlay.start)
        previous=overlay.end
    entry('blank.png',state.end-state.start-previous)
    entries.append("file 'blank.png'\noption framerate 1000\n")
    (folder/'overlays.txt').write_text(''.join(entries))
    return ['-f','concat','-safe','0','-i','overlays.txt'], ['-filter_complex',f'[0:v]{base_filter}[base];[base][1:v]overlay=0:0:format=auto[v]','-map','[v]','-map','0:a?']


def make_ass(cues, style, width, height):
    def color(hex_color, opacity=1):
        r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
        return f'&H{round((1-opacity)*255):02X}{b}{g}{r}'
    def stamp(seconds):
        cs = round(seconds*100)
        return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
    # Font size uses a 720px reference height in both preview and export.
    size = style.size * height / 720
    alignment = {'top':8, 'middle':5, 'bottom':2}[style.position]
    def style_line(name, primary, outline, border, thickness):
        return (f'Style: {name},{style.font},{size},{primary},&H00000000,{outline},{outline},'
                f'{-1 if style.bold else 0},0,0,0,100,100,0,0,{border},{thickness*height/720},0,'
                f'{alignment},{round(width*.08)},{round(width*.08)},{round(height*.08)},1\n')
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
'''
    header += style_line('Default', color(style.color), color(style.stroke), 1, style.thickness)
    if style.opacity:
        header += style_line('Background', color(style.color, 0), color(style.background, style.opacity), 3, 3)
    header += '[Events]\nFormat: Layer, Start, End, Style, Text\n'
    for cue in cues:
        # Neutralize ASS tags and line-break escapes from transcript data.
        text = cue['text'].replace('\\', '').replace('{', '').replace('}', '').replace('\n', r'\N')
        if style.opacity:
            header += f"Dialogue: 0,{stamp(cue['start'])},{stamp(cue['end'])},Background,{text}\n"
        header += f"Dialogue: 1,{stamp(cue['start'])},{stamp(cue['end'])},Default,{text}\n"
    return header
