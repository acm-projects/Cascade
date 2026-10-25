"""Owner-checked clip and wave research endpoints."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from backend import integration as store
from backend.research import grader, jobs

router = APIRouter()


class GradeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    use_edits: bool = True


@router.post('/api/projects/{pid}/clips/{jid}/{index}/grade', status_code=202)
def grade_clip(pid: str, jid: str, index: int, body: GradeInput, request: Request):
    result, cached = jobs.enqueue_clip(pid, jid, index, body.use_edits, request.state.user_id)
    return JSONResponse(result, status_code=200 if cached else 202, headers={'Cache-Control': 'no-store'})


@router.get('/api/projects/{pid}/clips/{jid}/{index}/grade')
def latest_grade(pid: str, jid: str, index: int, request: Request, use_edits: bool | None = None):
    with store.lock:
        grades = [grader.cached_grade(pid, jid, index, edited, request.state.user_id)
                  for edited in ([False, True] if use_edits is None else [use_edits])]
    grades = [grade for grade in grades if grade is not None]
    if not grades: raise HTTPException(404, 'No cached grade for this clip state. Grade it first.')
    return JSONResponse({'grade': max(grades, key=lambda g: g.graded_at).model_dump()}, headers={'Cache-Control': 'no-store'})


@router.post('/api/projects/{pid}/generations/{job_id}/grade', status_code=202)
def grade_wave(pid: str, job_id: str, request: Request):
    return {'job_id': jobs.enqueue_wave(pid, job_id, request.state.user_id)}
