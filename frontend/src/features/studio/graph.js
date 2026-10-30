export const clipKey = ref => `${ref.job_id}:${ref.clip_index}`;
export const sameRef = (a,b) => clipKey(a) === clipKey(b);

const groupReferences = group => group.parent_clips?.length ? group.parent_clips
  : group.parent_clip?.job_id ? [group.parent_clip]
  : group.studio_revision_of ? [group.studio_revision_of] : [];

// A new attempt replaces the previous visible branch from the same selected clips.
// Picked outputs and ancestors of visible branches must remain reachable.
export function visibleGenerationIds(session, groups, picked = []) {
  const ordered = sessionGroups(session, groups);
  const byId = new Map(ordered.map(group => [group.job_id, group]));
  const latest = new Map();
  for (const group of ordered) {
    const refs = groupReferences(group);
    const key = refs.length ? 'refs:' + refs.map(clipKey).sort().join('|')
      : 'source:' + (group.source_job || session.source_job || '') + ':' + (group.prompt
        ? group.prompt.trim().toLowerCase().replace(/\s+/g, ' ') : group.job_id);
    latest.set(key, group.job_id);
  }
  const visible = new Set();
  function retain(id) {
    if (visible.has(id) || !byId.has(id)) return;
    visible.add(id);
    for (const ref of groupReferences(byId.get(id))) retain(ref.job_id);
  }
  for (const id of latest.values()) retain(id);
  for (const ref of picked) retain(ref.job_id);
  return visible;
}

// Every result remains visible. Legacy replacement metadata no longer hides parents.
export function displayClips(session, groups, group) {
  return group.clips.map((clip,index)=>({clip,ref:{job_id:group.job_id,clip_index:index},label:String(index+1),revision:null}));
}

export function buildGraph(session, groups, actions) {
  const nodes=[], edges=[], placed=new Map(), depths=new Map(), bottoms=new Map();
  const sourceId='source:'+(session.source_job||'upload');
  const position=(id,fallback)=>session.positions?.[id]||fallback;
  nodes.push({id:sourceId,type:'source',position:position(sourceId,{x:0,y:320}),data:{session,...actions},draggable:true});
  const byId=new Map(groups.map(g=>[g.job_id,g]));
  const visible = actions.showHistory ? null : visibleGenerationIds(session, groups, actions.editorClips);
  let clipNumber=0;
  for(const [number,group] of session.job_ids.map(id=>byId.get(id)).filter(Boolean).entries()) {
    if (visible && !visible.has(group.job_id)) {
      clipNumber += group.clips.length;
      continue;
    }
    const refs=group.parent_clips?.length?group.parent_clips:group.parent_clip?.job_id?[group.parent_clip]:group.studio_revision_of?[group.studio_revision_of]:[];
    const depth=refs.length?1+Math.max(0,...refs.map(r=>depths.get(r.job_id)||0)):0;
    depths.set(group.job_id,depth);
    const parents=refs.map(r=>placed.get(clipKey(r))).filter(Boolean);
    const height=Math.max(1,group.clips.length)*300;
    const top=Math.max(0,parents.length?parents[0].y:0,bottoms.get(depth)||0);
    bottoms.set(depth,top+height+100);
    const hubId='generation:'+group.job_id;
    const combined=refs.length>1;
    const showHub=!refs.length||!group.clips.length||combined;
    const referenceLabels=refs.map(r=>{
      const parent=nodes.find(n=>n.id==='clip:'+clipKey(r));
      return {label:parent?.data.label||String(r.clip_index+1),title:parent?.data.clip.title||r.title||'Selected clip'};
    });
    // Combined requests stay visible as a merge point, including short results.
    if(showHub) {
      nodes.push({id:hubId,type:'generation',position:position(hubId,{x:480+depth*1050,y:top+height/2-60}),data:{group,number:number+1,referenceLabels,...actions}});
      for(const source of refs.length?refs.map(r=>'clip:'+clipKey(r)):[sourceId])
        edges.push({id:source+'>'+hubId,source,target:hubId,type:'vine',animated:['queued','processing'].includes(group.state)});
    }
    for(const [index,clip] of group.clips.entries()) {
      const ref={job_id:group.job_id,clip_index:index},id='clip:'+clipKey(ref);
      const pos=position(id,{x:900+depth*1050,y:top+index*300});
      placed.set(clipKey(ref),pos);
      nodes.push({id,type:'clip',position:pos,data:{clip,ref,label:String(++clipNumber),number:number+1,referenceLabels,...actions}});
      for(const source of showHub?[hubId]:refs.map(r=>'clip:'+clipKey(r)))
        edges.push({id:source+'>'+id,source,target:id,type:'vine',style:{stroke:'#719d87',strokeWidth:1.7}});
    }
  }
  const ids=new Set(nodes.map(n=>n.id));
  return {nodes,edges:edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
}

export function sessionGroups(session, groups) {
 const byId=new Map(groups.map(g=>[g.job_id,g]));
 return session.job_ids.map(id=>byId.get(id)).filter(Boolean);
}
