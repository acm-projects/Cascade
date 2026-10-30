"""Editor render; extracted without changing media behavior."""
import os
import re
import subprocess
import shutil
import zipfile
from functools import lru_cache
import tempfile
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from backend import reframe as reframelib
from .models import BatchExport, ExportInput
from .composition import composition_filter, composition_geometry, effects_filter, resolution_filter
from .validation import details, trimmed_cues, validate_edit, validate_media_edit
from .captions import make_ass, raster_filters
from .storage import media, selected, stock_store
from .reframe import begin_analysis, read_analysis

@lru_cache(maxsize=2)
def export_binary(needs_captions):
    binary = os.getenv('CASCADE_EDITOR_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg'
    if not needs_captions:
        return binary
    # Homebrew's minimal build omits libass; prefer an already-installed full build.
    candidates = [binary, str(Path(binary).parent.parent / 'opt/ffmpeg-full/bin/ffmpeg')]
    for candidate in candidates:
        try:
            filters = subprocess.run([candidate, '-hide_banner', '-filters'], capture_output=True, text=True, timeout=15, check=True).stdout
            if re.search(r'\bass\s+V->V', filters):
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    raise HTTPException(503, 'Caption export requires FFmpeg with libass. Set CASCADE_EDITOR_FFMPEG to a compatible binary on the server.')


def export_selected(pid: str, body: BatchExport, request: Request):
    # Authorize the entire selection before spending time on any render.
    seen = set()
    for entry in body.clips:
        key = (entry.job_id, entry.clip_index)
        if key in seen:
            raise HTTPException(422, 'Export selection contains duplicate clips.')
        seen.add(key)
        clip = selected(pid, entry.job_id, entry.clip_index, request.state.user_id)
        validate_media_edit(entry.edit, details(entry.job_id, clip))
        stock_store(pid, entry.job_id, entry.clip_index, request.state.user_id).verify(entry.edit)
    directory = tempfile.TemporaryDirectory(prefix='cascade-export-selection-')
    try:
        path = Path(directory.name)/'cascade-clips.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for number, entry in enumerate(body.clips, 1):
                response = export(pid, entry.job_id, entry.clip_index, entry.edit, request)
                try:
                    name = f'{number:03d}-clip-{entry.clip_index+1}-{entry.job_id[:8]}'
                    archive.write(response.path, name+Path(response.path).suffix)
                    captions = Path(response.path).with_suffix('.vtt')
                    if captions.is_file():
                        archive.write(captions, name+'.vtt')
                finally:
                    response.background.func(*response.background.args, **response.background.kwargs)
        return FileResponse(path, filename='cascade-clips.zip', media_type='application/zip', background=BackgroundTask(directory.cleanup))
    except Exception:
        directory.cleanup()
        raise


def export(pid: str, jid: str, index: int, body: ExportInput, request: Request):
    return _export(pid,jid,index,body,request)


def _export(pid, jid, index, body, request, prepared=None):
    clip = selected(pid, jid, index, request.state.user_id)
    info = prepared[2] if prepared else details(jid, clip)
    if prepared: body=ExportInput.model_validate(prepared[1].model_dump())
    validate_media_edit(body, info)
    stock=stock_store(pid,jid,index,request.state.user_id)
    stock.verify(body)
    from .audio_assets import store
    audio_store=store(pid,jid,index,request.state.user_id)
    audio_store.verify(body)
    if not prepared and (body.timeline or body.speed):
        if body.overlays is not None: raise HTTPException(422,'Retimed Reel captions must use server rendering, without source-timed raster overlays.')
        if info.get('has_video') is False: raise HTTPException(422,'Reel timeline retiming currently requires video.')
        from .retiming import prepare
        with media(jid,clip) as source, prepare(source,body,info,export_binary(False)) as prepared_source:
            return _export(pid,jid,index,prepared_source[1],request,prepared_source)
    directory = tempfile.TemporaryDirectory(prefix='cascade-export-')
    try:
        folder = Path(directory.name)
        if info.get('has_video') is False:
            from .audio import render_audio
            with media(jid, clip) as source:
                render_audio(source, folder, body, info['cues'], audio_store)
            return FileResponse(folder/'edited.mp3', filename='cascade-edited.mp3', media_type='audio/mpeg', background=BackgroundTask(directory.cleanup))
        g=composition_geometry(info['width'],info['height'],body.composition)
        base_filter=composition_filter(g,body.composition)
        needs_tracking=body.composition.mode=='fill' and (g['scaledWidth']>g['width'] or g['scaledHeight']>g['height'])
        if needs_tracking:
            if not body.reframe.analysis_id:
                begin_analysis(pid,jid,index,request.state.user_id,body.reframe.selection,body.reframe.focus)
                raise HTTPException(409,'Automatic framing is being prepared. Open Exports and retry when analysis is ready.')
            analysis=read_analysis(pid,jid,index,body.reframe.analysis_id,request.state.user_id)
            if analysis.get('selection')!=(body.reframe.selection.model_dump() if body.reframe.selection else None):raise HTTPException(409,'Selected subject tracking is outdated. Reopen the editor.')
            motion=reframelib.plan(analysis,g,body.reframe.focus,(.5,.5))
            x=reframelib.expression(motion['points'],'x',g['scaledWidth']-g['width'],body.start)
            y=reframelib.expression(motion['points'],'y',g['scaledHeight']-g['height'],body.start)
            base_filter=f"setpts=PTS-STARTPTS,scale={g['scaledWidth']}:{g['scaledHeight']}:flags=lanczos,setsar=1,crop={g['width']}:{g['height']}:x='{x}':y='{y}'"

        extra_inputs=[]
        graph=f'[0:v]{base_filter},setpts=PTS-STARTPTS[main0]'
        label='main0'
        input_index=1
        for segment in sorted(body.broll,key=lambda s:s.start):
            begin=max(body.start,segment.start); end=min(body.end,segment.start+segment.duration)
            if end<=begin: continue  # Hidden segments stay in the draft, recoverable by resetting trim.
            source=stock.media(segment.asset.id)
            extra_inputs.extend(['-ss',str(segment.offset+begin-segment.start),'-t',str(end-begin),'-i',str(source.resolve())])
            w,h=g['width'],g['height']
            if segment.mode=='fill':
                framing=f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h}'
            else:
                framing=f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{body.composition.background[1:]}'
            at=begin-body.start; until=end-body.start
            blend=''
            if segment.transition=='dissolve':
                fade=min(segment.transition_duration,(end-begin)/3)
                blend=f',format=yuva420p,fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={end-begin-fade}:d={fade}:alpha=1'
            graph+=f';[{input_index}:v]{framing},setsar=1,setpts=PTS-STARTPTS{blend},setpts=PTS+{at}/TB[stock{input_index}]'
            graph+=f";[{label}][stock{input_index}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{at})*lt(t,{until})'[main{input_index}]"
            label=f'main{input_index}'; input_index+=1
        from .timeline_render import motion_filter, transition_filter, audio_graph
        graph+=f';[{label}]{motion_filter(body,g["width"],g["height"])},{effects_filter(body.effects)}[effects]'
        label='effects'
        needs_ass=(body.overlays is None and body.captions.enabled and bool(info['cues'])) or bool(body.text_overlays)
        if body.overlays is not None and (body.captions.animation!='none' or body.text_overlays):
            raise HTTPException(422,'Animated captions/text require server rendering without raster overlays.')
        if body.overlays is not None:
            caption_inputs,caption_filters=raster_filters(folder,body.overlays,info['cues'],body,g['width'],g['height'])
            if caption_inputs:
                extra_inputs.extend(caption_inputs)
                graph+=f';[{label}][{input_index}:v]overlay=0:0:format=auto[out]'
            else:
                graph+=f';[{label}]null[out]'
            if caption_inputs: input_index+=1
        elif needs_ass:
            (folder/'captions.ass').write_text(make_ass(trimmed_cues(info['cues'],body) if body.captions.enabled else [],body.captions,g['width'],g['height'], body.text_overlays, body.start))
            graph+=f';[{label}]ass=captions.ass[out]'
        else:
            graph+=f';[{label}]null[out]'
        # Resize the completed composition, including captions and B-roll.
        graph = graph.replace('[out]', '[composed]')
        graph += f";[composed]{transition_filter(body)},{resolution_filter(g['width'], g['height'], body.resolution)}[out]"
        audio_inputs,audio_filters,audio_label=audio_graph(body,info['cues'],audio_store,info['has_audio'],input_index)
        extra_inputs.extend(audio_inputs)
        if audio_filters: graph+=';'+';'.join(audio_filters)
        audio_map=['-map',audio_label] if audio_label else []
        # Avoid OS argument limits for long crop trajectories. FFmpeg 7+ reads
        # option arguments from files; older releases use filter_complex_script.
        graph_args=['-filter_complex',graph]
        if len(graph)>60000:
            (folder/'filters.txt').write_text(graph)
            help_text=subprocess.run([export_binary(needs_ass),'-hide_banner','-h','full'],capture_output=True,text=True,timeout=15,check=True).stdout
            option='-filter_complex_script' if '-filter_complex_script' in help_text else '-/filter_complex'
            graph_args=[option,str(folder/'filters.txt')]
        from contextlib import nullcontext
        with (nullcontext(prepared[0]) if prepared else media(jid, clip)) as source:
            subprocess.run([export_binary(needs_ass), '-nostdin', '-v', 'error', '-y', '-ss', str(body.start), '-i', str(source.resolve()),
                            *extra_inputs, '-t', str(body.end-body.start), *graph_args,'-map','[out]',*audio_map,
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(folder/'edited.mp4')],
                           cwd=folder, capture_output=True, check=True, timeout=300)
        return FileResponse(folder/'edited.mp4', filename='cascade-edited.mp4', media_type='video/mp4', background=BackgroundTask(directory.cleanup))
    except (OSError, subprocess.SubprocessError):
        directory.cleanup()
        raise HTTPException(503, 'Export failed. Check FFmpeg with libass support and retry.')
    except Exception:
        directory.cleanup()
        raise
