export const clipKey = ref => `${ref.job_id}:${ref.clip_index}`;
export const sameRef = (a, b) => clipKey(a) === clipKey(b);

// Revisions fill the selected clip's existing slot. Actual media IDs remain intact
// for preview/editor ownership checks; original files stay recoverable on disk.
export function displayClips(session, groups, group) {
  const byId = new Map(groups.map(g=>[g.job_id,g]));
  const expand = (clip, ref, label, seen=new Set()) => {
    const key=clipKey(ref), replacement=session.clip_revisions?.[key];
    const revision=byId.get(typeof replacement==='string'?replacement:replacement?.job_id);
    if(revision && !seen.has(key) && revision.state==='done' && revision.clips.length) {
      const visited=new Set(seen);visited.add(key);
      const choices=revision.clips.map((clip,index)=>({clip,index})).filter(({index})=>
        typeof replacement==='string'||index%replacement.target_count===replacement.target_index);
      if(choices.length)return choices.flatMap(({clip:next,index},slot)=>expand(next,{job_id:revision.job_id,clip_index:index},
        choices.length===1?label:label+'.'+(slot+1),visited));
    }
    return [{clip,ref,label,revision:revision||null}];
  };
  return group.clips.flatMap((clip,index)=>expand(clip,{job_id:group.job_id,clip_index:index},String(index+1)));
}

// Stable node IDs and separate connections for every reference make multi-parent
// generations explicit. Persisted positions take precedence over auto-layout.
export function buildGraph(session, groups, actions) {
  const nodes = [], edges = [], placed = new Map(), depths = new Map(), bottoms = new Map();
  const sourceId = 'source:' + (session.source_job || 'upload');
  const position = (id, fallback) => session.positions?.[id] || fallback;
  nodes.push({id:sourceId, type:'source', position:position(sourceId,{x:0,y:320}),
    data:{session, ...actions}, draggable:true});
  const byId = new Map(groups.map(group => [group.job_id, group]));
  const revisions = new Set(Object.values(session.clip_revisions||{}).map(value=>typeof value==='string'?value:value.job_id));
  const ordered = session.job_ids.map(id => byId.get(id)).filter(g=>g&&!g.studio_revision_of&&!revisions.has(g.job_id));
  for (const [number, group] of ordered.entries()) {
    const refs = group.parent_clips?.length ? group.parent_clips : group.parent_clip?.job_id ? [group.parent_clip] : [];
    const depth = refs.length ? 1 + Math.max(0,...refs.map(ref => depths.get(ref.job_id) || 0)) : 0;
    depths.set(group.job_id, depth);
    const parents = refs.map(ref => placed.get(clipKey(ref))).filter(Boolean);
    const entries=displayClips(session,groups,group);
    const height = Math.max(1,entries.length) * 300;
    const desired = parents.length ? parents.reduce((sum,p)=>sum+p.y,0)/parents.length - height/2 : 0;
    const top = Math.max(0,desired,bottoms.get(depth) || 0);
    bottoms.set(depth,top+height+100);
    const hubId = 'generation:' + group.job_id;
    const hubPos = position(hubId,{x:350+depth*850,y:top+height/2-60});
    nodes.push({id:hubId,type:'generation',position:hubPos,data:{group:{...group,displayed_clip_count:entries.length,is_updated:entries.some(entry=>entry.ref.job_id!==group.job_id)},number:number+1,...actions}});
    const sources = refs.length ? refs.map(ref=>'clip:'+clipKey(ref)) : [sourceId];
    for(const [i,source] of sources.entries()) edges.push({id:source+'>'+hubId,source,target:hubId,type:'smoothstep',
      style:{stroke:refs.length>1?'#8b74ce':'#719d87',strokeWidth:refs.length>1?2.5:1.7},
      label:refs.length>1 && i===0 ? 'Combined references' : undefined,
      animated:['queued','processing'].includes(group.state)});
    for(const [index,entry] of entries.entries()) {
      const {clip,ref,label,revision}=entry;
      const id = 'clip:'+clipKey(ref);
      const pos = position(id,{x:650+depth*850,y:top+index*300});
      placed.set(clipKey(ref),pos);
      nodes.push({id,type:'clip',position:pos,data:{clip,ref,label,revision,number:number+1,...actions}});
      edges.push({id:hubId+'>'+id,source:hubId,target:id,type:'smoothstep',style:{stroke:'#719d87',strokeWidth:1.7}});
    }
  }
  // Do not draw a dangling edge if a legacy/deleted reference is unavailable.
  const ids = new Set(nodes.map(n=>n.id));
  return {nodes,edges:edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
}
