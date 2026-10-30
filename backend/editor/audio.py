"""Native audio exports and optional timed transcript sidecars."""
import subprocess
from .validation import trimmed_cues


def render_audio(source, folder, state, cues, audio_store=None):
    from .timeline_render import audio_graph
    inputs,filters,label=audio_graph(state,cues,audio_store,True,1)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(state.start),
        '-i', str(source), *inputs, '-t', str(state.end-state.start), '-filter_complex', ';'.join(filters), '-map', label, '-vn',
        '-c:a', 'libmp3lame', '-b:a', '192k', str(folder/'edited.mp3')],
        capture_output=True, check=True, timeout=300)
    if state.captions.enabled:
        def stamp(t):
            total = round(t*1000)
            return f'{total//3600000:02}:{total//60000%60:02}:{total//1000%60:02}.{total%1000:03}'
        text = 'WEBVTT\n\n' + '\n\n'.join(f"{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for c in trimmed_cues(cues,state))
        (folder/'edited.vtt').write_text(text+'\n', encoding='utf-8')
