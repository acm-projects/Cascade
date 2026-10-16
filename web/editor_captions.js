/* The same local rasterizer supplies live preview and caption pixels for export. */
window.CascadeCaptions = {
  intervals(cues,state) {
    const boundaries=[...new Set([state.start,state.end,...cues.flatMap(c=>[Math.max(state.start,Math.min(state.end,c.start)),Math.max(state.start,Math.min(state.end,c.end))])])].sort((a,b)=>a-b);
    return boundaries.slice(0,-1).map((start,i)=>({start:start-state.start,end:boundaries[i+1]-state.start,text:window.CascadeEditorState.cueAt(cues,(start+boundaries[i+1])/2,state)}));
  },
  draw(canvas,text,style,width,height) {
    if(canvas.width!==width) canvas.width=width; if(canvas.height!==height) canvas.height=height;
    const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,width,height); if(!text || !style.enabled) return;
    const scale=height/720, size=style.size*scale, lineHeight=size*1.2, padding=3*scale, maxWidth=width*.84-padding*2;
    ctx.font=(style.bold?'700 ':'400 ')+size+'px '+style.font;
    const lines=[];
    for(const paragraph of text.split('\n')) {
      let line='';
      for(const word of paragraph.split(/\s+/)) {
        if(line && ctx.measureText(line+' '+word).width>maxWidth) { lines.push(line); line=''; }
        // Break long words so preview and export stay inside the video.
        for(const char of (line?' ':'')+word) {
          if(line && ctx.measureText(line+char).width>maxWidth) { lines.push(line); line=''; }
          line+=char;
        }
      }
      lines.push(line);
    }
    const total=lines.length*lineHeight, y=style.position==='top'?height*.08:style.position==='middle'?(height-total)/2:height*.92-total;
    const blockWidth=Math.min(width*.84,Math.max(...lines.map(l=>ctx.measureText(l).width))+padding*2);
    ctx.globalAlpha=style.opacity; ctx.fillStyle=style.background; ctx.fillRect((width-blockWidth)/2,y-padding,blockWidth,total+padding*2); ctx.globalAlpha=1;
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.lineJoin='round'; ctx.strokeStyle=style.stroke; ctx.lineWidth=style.thickness*scale*2; ctx.fillStyle=style.color;
    lines.forEach((line,i)=>{ const baseline=y+(i+.5)*lineHeight; if(style.thickness) ctx.strokeText(line,width/2,baseline); ctx.fillText(line,width/2,baseline); });
  },
  exportFrames(cues,state,width,height) {
    if(!state.captions.enabled) return [];
    const canvas=document.createElement('canvas');
    return this.intervals(cues,state).filter(c=>c.text).map(c=>{
      this.draw(canvas,c.text,state.captions,width,height);
      return {start:c.start,end:c.end,png:canvas.toDataURL('image/png').split(',')[1]};
    });
  }
};
