/* Shared nested navigation; selection and opening a clip are independent actions. */
window.CascadeClipNavigation=class {
  constructor({container,items,selected=[],selectable=false,onOpen,onSelection}) {
    this.items=items;this.selected=new Set(selected);this.groups=[];this.buttons=new Map();this.leaves=[];
    container.replaceChildren();const sessions=new Map();
    const group=(label,parent,keys)=>{
      const details=document.createElement('details');details.className='clip-nav-group';
      const summary=document.createElement('summary');const title=document.createElement('span');title.textContent=label;
      details.append(summary);parent.append(details);
      if(selectable){const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('aria-label','Select all clips in '+label);
        checkbox.onclick=event=>event.stopPropagation();checkbox.onchange=()=>this.change(keys,checkbox.checked);summary.append(checkbox);this.groups.push({checkbox,keys});}
      summary.append(title);return details;
    };
    for(const item of items){const sid=item.wave.session_id||'session-'+(item.wave.session_number||1);if(!sessions.has(sid))sessions.set(sid,[]);sessions.get(sid).push(item);}
    for(const children of sessions.values()){
      const session=group(children[0].wave.session_name||'Session '+(children[0].wave.session_number||1),container,children.map(i=>i.key));const waves=new Map();
      for(const item of children){const wid=item.wave.wave_id||item.wave.job_id;if(!waves.has(wid))waves.set(wid,[]);waves.get(wid).push(item);}
      for(const clips of waves.values()){
        const wave=group('Wave '+(clips[0].wave.wave_number||1),session,clips.map(i=>i.key));wave.classList.add('clip-nav-wave');
        for(const item of clips){const row=document.createElement('div');row.className='clip-nav-row';
          if(selectable){const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('aria-label','Select '+item.label+' for export');checkbox.checked=this.selected.has(item.key);checkbox.onchange=()=>this.change([item.key],checkbox.checked);row.append(checkbox);this.leaves.push({checkbox,key:item.key});}
          const button=document.createElement('button');button.type='button';button.className='mini-clip';button.dataset.key=item.key;button.textContent='Clip '+item.number;button.title=item.clip?.title||item.label;button.onclick=()=>onOpen(item);row.append(button);wave.append(row);this.buttons.set(item.key,button);
        }
      }
    }
    this.onSelection=onSelection;this.refresh();
  }
  change(keys,checked){const previous=new Set(this.selected);for(const key of keys)if(checked)this.selected.add(key);else this.selected.delete(key);
    try{if(this.onSelection?.([...this.selected])===false){this.selected=previous;this.refresh();return;}}catch(error){this.selected=previous;this.refresh();throw error;}this.refresh();}
  refresh(){for(const {checkbox,key}of this.leaves)checkbox.checked=this.selected.has(key);
    for(const {checkbox,keys}of this.groups){const count=keys.filter(k=>this.selected.has(k)).length;checkbox.checked=count===keys.length&&!!count;checkbox.indeterminate=count>0&&count<keys.length;checkbox.setAttribute('aria-checked',checkbox.indeterminate?'mixed':String(checkbox.checked));}}
  active(key){for(const [id,button]of this.buttons){const active=id===key;button.classList.toggle('active',active);button.setAttribute('aria-current',String(active));button.setAttribute('aria-pressed',String(active));if(active){let parent=button.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}}}}
};
