"""Derived labels; existing job ancestry remains the source of truth."""
def label_waves(rows):
    by_id = {row['job_id']: row for row in rows}
    sessions, counts, explorations, waves = {}, {}, {}, {}
    for row in rows:
        root = row
        seen = set()
        while root.get('parent_clip') and root['job_id'] not in seen:
            seen.add(root['job_id'])
            parent = by_id.get(root['parent_clip'].get('job_id'))
            if not parent:
                break
            root = parent
        # Legacy history_id identifies a generation request, not a Session.
        # Repeated searches with identical source+prompt are additional Waves.
        source=root.get('source_job') or root['job_id']
        prompt=' '.join(root.get('prompt','').split()).casefold()
        exploration=(source,prompt) if prompt else (source,root['job_id'])
        sid=root.get('session_id') or explorations.setdefault(exploration,root['job_id'])
        if sid not in sessions:
            sessions[sid] = len(sessions) + 1
        wid=row.get('wave_id') or row['job_id']
        if (sid,wid) not in waves:
            counts[sid]=counts.get(sid,0)+1
            waves[(sid,wid)]=counts[sid]
        row.update(session_id=sid,wave_id=wid,session_number=sessions[sid],session_prompt=root.get('prompt',''),wave_number=waves[(sid,wid)])
    return rows
