"""Native audio exports and optional timed transcript sidecars."""
import subprocess
from .validation import trimmed_cues


def render_audio(source, folder, state, cues):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(state.start),
        '-i', str(source), '-t', str(state.end-state.start), '-map', '0:a:0', '-vn',
        '-c:a', 'libmp3lame', '-b:a', '192k', str(folder/'edited.mp3')],
        capture_output=True, check=True, timeout=300)
    if state.captions.enabled:
        def stamp(t):
            total = round(t*1000)
            return f'{total//3600000:02}:{total//60000%60:02}:{total//1000%60:02}.{total%1000:03}'
        text = 'WEBVTT\n\n' + '\n\n'.join(f"{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for c in trimmed_cues(cues,state))
        (folder/'edited.vtt').write_text(text+'\n', encoding='utf-8')
