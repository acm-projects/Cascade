/* Pure editor state helpers, shared by browser and focused Node tests. */
(function(root) {
  const defaultComposition={ratio:'original',mode:'fit',x:.5,y:.5,background:'#06110d'};
  const clone = value => JSON.parse(JSON.stringify(value));
  function normalize(state, duration) {
    if (!state || typeof state !== 'object') throw Error('Saved editing state is invalid.');
    const s = clone(state);
    if (!Number.isFinite(duration) || duration < .05) throw Error('Media duration is unavailable.');
    s.start = Math.max(0, Math.min(Number(s.start) || 0, duration - .05));
    s.end = Math.min(duration, Math.max(s.start + .05, Math.min(Number(s.end) || duration, duration)));
    s.broll = s.broll || [];
    validateBroll(s.broll,duration);
    s.texts = s.texts || {};
    if (typeof s.texts !== 'object' || Array.isArray(s.texts) || Object.entries(s.texts).some(([key,text]) => !/^\d+$/.test(key) || typeof text !== 'string' || text.length>2000)) throw Error('Saved caption text is invalid.');
    s.composition = {...defaultComposition, ...s.composition};
    const f=s.composition;
    if(!['original','9:16','1:1','4:5','16:9','4:3'].includes(f.ratio) || !['fit','fill'].includes(f.mode) ||
       !Number.isFinite(f.x) || f.x<0 || f.x>1 || !Number.isFinite(f.y) || f.y<0 || f.y>1 || !/^#[0-9a-f]{6}$/i.test(f.background)) throw Error('Saved framing is invalid.');
    const c = s.captions;
    if (!c || typeof c.enabled !== 'boolean' || typeof c.bold !== 'boolean' ||
        !['Arial','Georgia','Verdana'].includes(c.font) || !['top','middle','bottom'].includes(c.position) ||
        !['color','stroke','background'].every(k => /^#[0-9a-f]{6}$/i.test(c[k])) ||
        !Number.isInteger(c.size) || c.size < 12 || c.size > 80 ||
        !Number.isFinite(c.thickness) || c.thickness < 0 || c.thickness > 8 ||
        !Number.isFinite(c.opacity) || c.opacity < 0 || c.opacity > 1)
      throw Error('Saved caption settings are invalid.');
    return s;
  }
  function validateBroll(segments,duration) {
    if(!Array.isArray(segments) || segments.length>30) throw Error('Use at most 30 B-roll segments.');
    const ids=new Set(); let end=0;
    for(const s of [...segments].sort((a,b)=>a.start-b.start)) {
      if(!/^[a-f0-9]{32}$/.test(s.id) || ids.has(s.id) || !/^px-[0-9]+-[0-9]+$/.test(s.asset?.id) ||
         ![s.start,s.duration,s.offset,s.asset.duration].every(Number.isFinite) || s.start<0 || s.duration<.05 || s.offset<0 ||
         s.start+s.duration>duration+1e-6 || s.offset+s.duration>s.asset.duration+1e-6 || !['fit','fill'].includes(s.mode))
        throw Error('B-roll timing must fit the generated clip and stock footage. Check duration and source offset.');
      if(s.start<end-1e-6) throw Error('B-roll segments cannot overlap. Move or shorten a segment first.');
      ids.add(s.id); end=s.start+s.duration;
    }
    return segments;
  }
  class History {
    constructor(state) { this.state = clone(state); this.undoStack = []; this.redoStack = []; }
    commit(next) {
      if (JSON.stringify(this.state) === JSON.stringify(next)) return false;
      this.undoStack.push(clone(this.state));
      if (this.undoStack.length > 100) this.undoStack.shift();
      this.state = clone(next); this.redoStack = []; return true;
    }
    undo() { if (this.undoStack.length) { this.redoStack.push(clone(this.state)); this.state = this.undoStack.pop(); return true; } return false; }
    redo() { if (this.redoStack.length) { this.undoStack.push(clone(this.state)); this.state = this.redoStack.pop(); return true; } return false; }
  }
  function cueAt(cues, time, state) {
    if (!state.captions.enabled || time < state.start || time >= state.end) return '';
    return cues.map((c,index) => ({...c,text:state.texts?.[index]??c.text})).filter(c => time >= c.start && time < c.end).map(c => c.text).join('\n');
  }
  function formatTime(seconds) { const s=Math.max(0,seconds||0); return Math.floor(s/60)+':'+(s%60).toFixed(2).padStart(5,'0'); }
  function compositionGeometry(sourceWidth,sourceHeight,settings=defaultComposition) {
    const even=n=>Math.max(2,2*Math.floor(n/2+.5));
    let width=even(sourceWidth),height=even(sourceHeight);
    if(settings.ratio!=='original') {
      const [a,b]=settings.ratio.split(':').map(Number), unit=even(Math.max(sourceWidth,sourceHeight)/Math.max(a,b));
      width=a*unit; height=b*unit;
    }
    const scale=settings.mode==='fill'?Math.max(width/sourceWidth,height/sourceHeight):Math.min(width/sourceWidth,height/sourceHeight);
    let scaledWidth=even(sourceWidth*scale),scaledHeight=even(sourceHeight*scale),x,y;
    if(settings.mode==='fill') {
      scaledWidth=Math.max(width,scaledWidth); scaledHeight=Math.max(height,scaledHeight);
      x=2*Math.floor((scaledWidth-width)*settings.x/2+.5); y=2*Math.floor((scaledHeight-height)*settings.y/2+.5);
    } else {
      scaledWidth=Math.min(width,scaledWidth); scaledHeight=Math.min(height,scaledHeight);
      x=2*Math.floor((width-scaledWidth)/4); y=2*Math.floor((height-scaledHeight)/4);
    }
    return {width,height,scaledWidth,scaledHeight,x,y};
  }
  const api = {validateBroll,defaultComposition, compositionGeometry,clone, normalize, History, cueAt, formatTime};
  if (typeof module !== 'undefined') module.exports = api;
  else root.CascadeEditorState = api;
})(typeof window === 'undefined' ? globalThis : window);
