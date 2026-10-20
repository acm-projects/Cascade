/* Stable branch placement from persisted job IDs; labels are presentation only. */
(function(root) {
  function layout(groups) {
    const byId=new Map(groups.map(g=>[g.job_id,g])),positions={};
    let column=0;
    function visit(g,trail=new Set()) {
      if(positions[g.job_id] || trail.has(g.job_id))return;
      const path=new Set(trail);path.add(g.job_id);
      const parentId=g.parent_clip?.job_id || null;
      const parent=byId.get(parentId);
      if(parent && parent!==g)visit(parent,path);
      // Each request owns a unique horizontal slot, including siblings and
      // full-video searches. Only ancestry determines the logical depth.
      positions[g.job_id]={column:2+2*column,promptColumn:1+2*column++,row:0,depth:positions[parentId]?positions[parentId].depth+1:0,parentId};
    }
    groups.forEach(g=>visit(g));
    return positions;
  }
  const api={layout};
  if(typeof module==='object' && module.exports)module.exports=api;
  else root.CascadeBranches=api;
})(typeof window==='undefined'?globalThis:window);
