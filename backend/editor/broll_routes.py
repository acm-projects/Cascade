"""Owner-scoped stock search and media delivery."""
from fastapi import Request
from fastapi.responses import FileResponse
from .storage import selected, stock_store

def stock_search(pid: str, jid: str, index: int, request: Request, query: str, page: int = 1):
    selected(pid,jid,index,request.state.user_id)
    return stock_store(pid,jid,index,request.state.user_id).search(query,page)

def stock_media(pid: str, jid: str, index: int, asset_id: str, request: Request):
    selected(pid,jid,index,request.state.user_id)
    path=stock_store(pid,jid,index,request.state.user_id).media(asset_id)
    return FileResponse(path,media_type='video/mp4')

def stock_thumbnail(pid: str, jid: str, index: int, asset_id: str, request: Request):
    selected(pid,jid,index,request.state.user_id)
    path=stock_store(pid,jid,index,request.state.user_id).media(asset_id,image=True)
    return FileResponse(path,media_type='image/jpeg')
