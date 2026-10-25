"""Owner-scoped session and selection API."""
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator
from backend import integration as store
from backend.services import sessions

router = APIRouter()


class SessionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class RenameInput(SessionInput):
    name: str = Field(min_length=1, max_length=60)


class SelectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str
    clip_index: int = Field(strict=True, ge=0)


def project(pid, request):
    return store.require_project(pid, request.state.user_id)


@router.get('/api/projects/{pid}/sessions')
def list_sessions(pid: str, request: Request):
    with store.lock:
        data = project(pid, request)
        jobs = store.project_jobs(pid, request.state.user_id)
        return {'sessions': [{**s, 'wave_count': sum(j['kind'] == 'generation' and j['session_id'] == s['id'] for j in jobs)}
                             for s in sessions.list_sessions(data)]}


@router.post('/api/projects/{pid}/sessions', status_code=201)
def create_session(pid: str, body: SessionInput, request: Request):
    with store.lock:
        return sessions.create_session(project(pid, request), body.name)


@router.patch('/api/projects/{pid}/sessions/{sid}')
def rename_session(pid: str, sid: str, body: RenameInput, request: Request):
    with store.lock:
        return sessions.rename_session(project(pid, request), sid, body.name)


@router.delete('/api/projects/{pid}/sessions/{sid}', status_code=204)
def delete_session(pid: str, sid: str, request: Request):
    with store.lock:
        sessions.delete_session(project(pid, request), sid)
    return Response(status_code=204)


@router.get('/api/projects/{pid}/sessions/{sid}/selections')
def session_selections(pid: str, sid: str, request: Request):
    with store.lock:
        return {'selections': sessions.list_selections(project(pid, request), sid)}


@router.post('/api/projects/{pid}/sessions/{sid}/selections', status_code=201)
def add_selection(pid: str, sid: str, body: SelectionInput, request: Request):
    with store.lock:
        data = project(pid, request)
        entry, created = sessions.add_selection(data, sid, body.job_id, body.clip_index)
        result = next(s for s in sessions.list_selections(data, sid) if s['number'] == entry['number'])
        return JSONResponse(result, status_code=201 if created else 200)


@router.delete('/api/projects/{pid}/sessions/{sid}/selections/{number}', status_code=204)
def remove_selection(pid: str, sid: str, number: int, request: Request):
    with store.lock:
        sessions.remove_selection(project(pid, request), sid, number)
    return Response(status_code=204)


@router.get('/api/projects/{pid}/selections')
def project_selections(pid: str, request: Request):
    with store.lock:
        return {'selections': sessions.list_selections(project(pid, request))}
