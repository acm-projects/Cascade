"""Editor render; extracted without changing media behavior."""
import os
import re
import subprocess
import shutil
import zipfile
from contextlib import contextmanager
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


@contextmanager
def styled_media(jid, clip, body):
    """Clip media, with any stylized fan-edit effects baked in (cached, rendered locally)."""
    with media(jid, clip) as source:
        if not body.stylize or not body.stylize.events:
            yield source
            return
        from .stylize import stylized
        from .runtime import jobs_dir
        with stylized(source, body, jobs_dir()/jid/'stylize'/Path(source).stem) as path:
            yield path


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


def recompose_file(path, body):
    """Put a finished video (an AI edit) into the frame shape chosen in the Aspect tab: one quick FFmpeg pass, audio untouched."""
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',str(path)],capture_output=True,text=True,timeout=30)
    try:width,height=map(int,probe.stdout.strip().split('x'))
    except ValueError:raise HTTPException(503,'Could not read the finished edit. Try again.')
    g=composition_geometry(width,height,body.composition)
    filters=composition_filter(g,body.composition)
    if body.resolution!='original':filters+=','+resolution_filter(g['width'],g['height'],body.resolution)
    directory=tempfile.TemporaryDirectory(prefix='cascade-reshape-')
    target=Path(directory.name)/'edited.mp4'
    try:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(path),'-vf',filters,'-c:v','libx264','-preset','ultrafast' if body.preview else 'veryfast','-crf','26' if body.preview else '18',
                        '-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(target)],capture_output=True,check=True,timeout=300)
    except (OSError,subprocess.SubprocessError):
        directory.cleanup();raise HTTPException(503,'Could not reshape the edit. Check FFmpeg and retry.')
    return FileResponse(target,filename='cascade-edited.mp4',media_type='video/mp4',background=BackgroundTask(directory.cleanup))


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
    if body.ai_edit and not prepared:  # a finished AI edit: this exact file is what the preview showed
        from .ai_edit.jobs import rendered_path
        finished=rendered_path(pid, jid, index, request.state.user_id, body.ai_edit.version)
        if body.composition.ratio=='original':
            return FileResponse(finished, filename='cascade-edited.mp4', media_type='video/mp4', background=BackgroundTask(lambda: None))
        return recompose_file(finished, body)
    if body.fablecut and not prepared:
        if body.overlays is not None:
            raise HTTPException(422,'FableCut sequences render captions on the server; source raster overlays are unsupported.')
        from .sequence_models import OPENCHATCUT_ENGINE
        if body.fablecut.engine == OPENCHATCUT_ENGINE:
            from .openchatcut_render import render as render_sequence
        else:
            from .fablecut_render import render as render_sequence
        from .storage import draft_path
        import hashlib
        import json
        from .runtime import jobs_dir
        cache=draft_path(pid,jid,index,request.state.user_id).parent/'sequence-renders'/f'{jid}-{index}'
        cache.mkdir(parents=True,exist_ok=True)
        local_source=jobs_dir()/jid/Path(clip.get('clip_url','')).name
        version=(local_source.stat().st_size,local_source.stat().st_mtime_ns) if local_source.is_file() else clip.get('clip_s3_key')
        digest=hashlib.sha256(json.dumps({'state':body.model_dump(),'info':info,'clip':clip,'source_version':version,'renderer':hashlib.sha256(b''.join(p.read_bytes() for p in sorted([*Path(__file__).parent.glob('*.py'),*Path(__file__).parent.glob('*.mts')]))).hexdigest()},sort_keys=True).encode()).hexdigest()
        cached=cache/(digest+'.mp4')
        if cached.is_file():
            return FileResponse(cached,filename='cascade-edited.mp4',media_type='video/mp4',background=BackgroundTask(lambda:None))
        result_dir=tempfile.TemporaryDirectory(prefix='cascade-sequence-export-')
        base_response=None
        try:
            base=body.model_copy(deep=True);base.fablecut=None;base.captions.enabled=False;base.audio=[]
            base_response=_export(pid,jid,index,base,request)
            output=Path(result_dir.name)/'edited.mp4'
            render_sequence(base_response.path,output,body,info,audio_store)
            staged=cache/(digest+'.'+os.urandom(6).hex()+'.tmp')
            shutil.copy2(output,staged);os.replace(staged,cached)
            return FileResponse(output,filename='cascade-edited.mp4',media_type='video/mp4',background=BackgroundTask(result_dir.cleanup))
        except Exception:
            result_dir.cleanup();raise
        finally:
            if base_response and base_response.background:
                base_response.background.func(*base_response.background.args,**base_response.background.kwargs)
    if not prepared and (body.timeline or body.speed):
        if body.overlays is not None: raise HTTPException(422,'Retimed Reel captions must use server rendering, without source-timed raster overlays.')
        if info.get('has_video') is False: raise HTTPException(422,'Reel timeline retiming currently requires video.')
        from .retiming import prepare
        with styled_media(jid,clip,body) as source, prepare(source,body,info,export_binary(False)) as prepared_source:
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
            analysis_id=body.reframe.analysis_id
            if not analysis_id:
                # A finished analysis is found by its content key, so the draft doesn't have to carry its id.
                started=begin_analysis(pid,jid,index,request.state.user_id,body.reframe.selection,body.reframe.focus)
                if started.get('status')=='ready':analysis_id=started['analysis_id']
                elif not body.preview:
                    raise HTTPException(409,'Automatic framing is being prepared. Open Exports and retry when analysis is ready.')
            analysis=None
            if analysis_id:
                try:analysis=read_analysis(pid,jid,index,analysis_id,request.state.user_id)
                except HTTPException:
                    if not body.preview:raise
            if analysis is not None:
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
        with (nullcontext(prepared[0]) if prepared else styled_media(jid, clip, body)) as source:
            subprocess.run([export_binary(needs_ass), '-nostdin', '-v', 'error', '-y', '-ss', str(body.start), '-i', str(source.resolve()),
                            *extra_inputs, '-t', str(body.end-body.start), *graph_args,'-map','[out]',*audio_map,
                            '-c:v', 'libx264', '-preset', 'ultrafast' if body.preview else 'veryfast', '-crf', '26' if body.preview else '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(folder/'edited.mp4')],
                           cwd=folder, capture_output=True, check=True, timeout=300)
        return FileResponse(folder/'edited.mp4', filename='cascade-edited.mp4', media_type='video/mp4', background=BackgroundTask(directory.cleanup))
    except (OSError, subprocess.SubprocessError):
        directory.cleanup()
        raise HTTPException(503, 'Export failed. Check FFmpeg with libass support and retry.')
    except Exception:
        directory.cleanup()
        raise
