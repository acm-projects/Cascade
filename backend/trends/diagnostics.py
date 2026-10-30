"""Stage diagnostics that never log credentials or signed request URLs."""
import json
import logging
import os
import re
import time
import shutil
import tempfile
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG=logging.getLogger('cascade.trends')
RESEARCH_ID=ContextVar('cascade_research_id',default='unassigned')
# A small local trace survives browser failures; it contains only sanitized stage
# messages, never request headers, raw provider payloads, transcripts or keys.
TRACE_PATH=Path(tempfile.gettempdir())/f'cascade-trends-{os.getpid()}.log'
if not any(getattr(h,'cascade_stage_trace',False) for h in LOG.handlers):
    class ResearchFilter(logging.Filter):
        def filter(self,record):record.research_id=RESEARCH_ID.get();return True
    handler=RotatingFileHandler(TRACE_PATH,maxBytes=2_000_000,backupCount=1,encoding='utf-8')
    handler.cascade_stage_trace=True
    handler.addFilter(ResearchFilter())
    handler.setFormatter(logging.Formatter('%(asctime)s [research=%(research_id)s] %(levelname)s %(message)s'))
    LOG.addHandler(handler);LOG.setLevel(logging.INFO)

def ydl_options():
    class SafeLogger:
        def debug(self,message):pass
        def warning(self,message):LOG.warning('YouTube: %s',safe_text(message))
        def error(self,message):LOG.error('YouTube: %s',safe_text(message))
    options={'quiet':True,'socket_timeout':25,'retries':1,'extractor_retries':1,'logger':SafeLogger()}
    node=shutil.which('node')
    if node:options['js_runtimes']={'node':{'path':node}}
    return options

def safe_text(error):
    text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',str(error))
    for name,value in os.environ.items():
        if len(value)>5 and any(k in name.upper() for k in ('KEY','SECRET','TOKEN','PASSWORD','DATABASE_URL')):
            text=text.replace(value,'[redacted]')
    text=re.sub(r'https?://[^\s\"\'<>]+',lambda m:m.group(0).split('?')[0].split('#')[0],text)
    text=re.sub(r'(?i)(authorization|bearer|token)[=: ]+\S+',r'\1 [redacted]',text)
    return text[:700]

def failure(error,stage,reference=None):
    status=getattr(error,'status_code',None) or getattr(getattr(error,'resp',None),'status',None)
    message=safe_text(error);lower=message.lower();reason=None
    try:
        data=json.loads(getattr(error,'content',b'{}'))
        reason=next((r.get('reason') for r in data.get('error',{}).get('errors',[]) if r.get('reason')),None)
    except (ValueError,TypeError):pass
    if reason in ('quotaExceeded','dailyLimitExceeded') or status==402:code='quota_or_credit_exhausted'
    elif status==429 or 'rate limit' in lower:code='rate_limited'
    elif status==401 or reason in ('keyInvalid','authError','accessNotConfigured'):code='authentication'
    elif status==404 and stage.startswith('ai'):code='model_unavailable'
    elif status==403 and stage=='discovery':code='permission_or_api_disabled'
    elif 'duration' in lower and 'limit' in lower:code='reference_too_long'
    elif 'not set' in lower or 'not configured' in lower:code='configuration'
    elif 'not a bot' in lower or 'confirm you' in lower:code='youtube_bot_challenge'
    elif 'sign in' in lower or 'login' in lower or status==403:code='authentication_or_access'
    elif any(s in lower for s in ('private video','video unavailable','video is unavailable','video is not available','video has been removed','copyright','not available in your country')):code='video_unavailable'
    elif 'requested format' in lower:code='download_format_unavailable'
    elif 'timeout' in lower or 'timed out' in lower:code='timeout'
    elif stage=='download':code='download_failed'
    elif stage in ('video_frames','audio_extract','render'):code='media_extraction_failed'
    elif stage=='transcription':code='transcription_failed'
    elif stage.startswith('ai'):code='ai_failed'
    else:code='request_failed'
    return {'stage':stage,'code':code,'status':status,'provider_reason':reason,'reason':message,'reference_id':reference}

class StageError(RuntimeError):
    def __init__(self,detail):self.detail=detail;super().__init__(detail['stage']+': '+detail['code']+' — '+detail['reason'])

class ResearchFailure(RuntimeError):
    def __init__(self,message,failures,references=()):
        self.failures=failures;self.references=list(references);super().__init__(message)

def stage(label,fn,*args,reference=None,**kwargs):
    started=time.monotonic()
    try:
        result=fn(*args,**kwargs)
        LOG.info('research stage=%s reference=%s status=ok elapsed=%.2fs',label,reference,time.monotonic()-started)
        return result
    except (StageError,ResearchFailure):raise
    except Exception as exc:
        detail=failure(exc,label,reference)
        LOG.error('research stage=%s reference=%s code=%s status=%s detail=%s',label,reference,detail['code'],detail['status'],detail['reason'])
        raise StageError(detail) from None
