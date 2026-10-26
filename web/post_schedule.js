/* Local wall-clock dates are resolved explicitly in the chosen IANA zone, including DST folds. */
window.CascadeScheduleTime={
  parts(instant,zone){const out={};for(const part of new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(instant)))if(part.type!=='literal')out[part.type]=part.value;return out;},
  date(instant,zone){const p=this.parts(instant,zone);return `${p.year}-${p.month}-${p.day}`;},
  candidates(wall,zone){
    const [year,month,day,hour,minute]=wall.split(/[-T:]/).map(Number),guess=Date.UTC(year,month-1,day,hour,minute),offsets=new Set(),result=[];
    for(let delta=-48;delta<=48;delta+=6){const sample=guess+delta*3600000,p=this.parts(sample,zone);offsets.add((Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute)-sample)/60000);}
    for(const offset of offsets){const instant=guess-offset*60000,p=this.parts(instant,zone);if(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`===wall)result.push({instant,offset});}
    return result.sort((a,b)=>a.instant-b.instant);
  },
  format(schedule){if(!schedule)return '';const [date,time]=schedule.local_datetime.split('T'),[year,month,day]=date.split('-').map(Number),[hour,minute]=time.split(':').map(Number);return `${new Intl.DateTimeFormat('en-US',{month:'long',day:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(year,month-1,day)))} at ${hour%12||12}:${String(minute).padStart(2,'0')} ${hour<12?'AM':'PM'} · ${schedule.timezone}`;}
};

window.CascadeSchedulePicker=class {
  constructor({container,draft,onChange}){
    this.onChange=onChange;this.time=window.CascadeScheduleTime;this.draft=draft;
    const zone=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
    if(!draft.timezone){const p=this.time.parts(Date.now()+2*3600000,zone);Object.assign(draft,{timezone:zone,date:`${p.year}-${p.month}-${p.day}`,hour:String(+p.hour%12||12),minute:p.minute,period:+p.hour<12?'AM':'PM'});}
    this.month=draft.date.slice(0,7);this.open=true;
    const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text)node.textContent=text;return node;};
    const button=(text,fn)=>{const b=el('button','',text);b.type='button';b.onclick=fn;return b;};
    this.root=el('div','schedule-picker');container.append(this.root);
    this.trigger=button('Choose date & time',()=>this.setOpen(!this.open));this.trigger.className='schedule-trigger';this.root.append(this.trigger);
    this.popover=el('div','schedule-popover');this.popover.id='schedule-calendar-'+crypto.randomUUID();this.popover.setAttribute('role','group');this.popover.setAttribute('aria-label','Schedule date and time');this.trigger.setAttribute('aria-controls',this.popover.id);this.root.append(this.popover);
    const header=el('div','schedule-month');this.previous=button('‹',()=>this.moveMonth(-1));this.previous.setAttribute('aria-label','Previous month');this.next=button('›',()=>this.moveMonth(1));this.next.setAttribute('aria-label','Next month');this.monthLabel=el('strong');this.monthLabel.setAttribute('aria-live','polite');header.append(this.previous,this.monthLabel,this.next);this.popover.append(header);
    this.grid=el('div','schedule-calendar');this.grid.setAttribute('role','grid');this.grid.setAttribute('aria-label','Publication date');this.popover.append(this.grid);
    this.dateError=el('p','schedule-error');this.dateError.id=this.popover.id+'-date-error';this.dateError.setAttribute('role','status');this.grid.setAttribute('aria-describedby',this.dateError.id);this.popover.append(this.dateError);
    const clock=el('div','schedule-clock');
    const select=(label,values,value)=>{const wrap=el('label','',label),input=el('select');for(const v of values){const option=el('option','',v);option.value=v;input.append(option);}input.value=value;wrap.append(input);clock.append(wrap);input.onchange=()=>{this.readClock();this.validate();};return input;};
    this.hour=select('Hour',Array.from({length:12},(_,i)=>String(i+1)),draft.hour);this.minute=select('Minute',Array.from({length:60},(_,i)=>String(i).padStart(2,'0')),draft.minute);this.period=select('AM / PM',['AM','PM'],draft.period);this.popover.append(clock);
    const timezoneLabel=el('label','schedule-zone','Timezone');this.zone=el('select');const zones=[...new Set([draft.timezone,zone,'UTC',...(Intl.supportedValuesOf?Intl.supportedValuesOf('timeZone'):['America/Chicago','America/New_York','America/Los_Angeles','Europe/London','Asia/Tokyo'])])].sort();for(const value of zones){const option=el('option','',value);option.value=value;this.zone.append(option);}this.zone.value=draft.timezone;timezoneLabel.append(this.zone);this.popover.append(timezoneLabel);
    this.zone.onchange=()=>{draft.timezone=this.zone.value;draft.offset=null;this.draw();this.validate();};
    const repeatLabel=el('label','schedule-zone','Repeated hour');this.repeat=el('select');repeatLabel.append(this.repeat);this.repeatLabel=repeatLabel;this.popover.append(repeatLabel);this.repeat.onchange=()=>{draft.offset=Number(this.repeat.value);this.validate();};
    this.timeError=el('p','schedule-error');this.timeError.id=this.popover.id+'-time-error';this.timeError.setAttribute('role','status');this.popover.append(this.timeError);for(const input of [this.hour,this.minute,this.period,this.zone,this.repeat])input.setAttribute('aria-describedby',this.timeError.id);
    const done=button('Done',()=>{if(this.validate())this.setOpen(false);});done.className='schedule-done';this.popover.append(done);
    this.summary=el('p','schedule-summary');this.summary.setAttribute('aria-live','polite');this.root.append(this.summary);
    this.root.addEventListener('keydown',event=>{if(event.key==='Escape'&&this.open){event.stopPropagation();event.preventDefault();this.setOpen(false);this.trigger.focus();}});
    this.draw();this.setOpen(true);this.validate(false);
  }
  setDisabled(disabled){this.lockedControls ||= new Map();for(const input of this.root.querySelectorAll('button,select')){if(disabled){if(!this.lockedControls.has(input))this.lockedControls.set(input,input.disabled);input.disabled=true;}else if(this.lockedControls.has(input)){input.disabled=this.lockedControls.get(input);this.lockedControls.delete(input);}}}
  readClock(){Object.assign(this.draft,{hour:this.hour.value,minute:this.minute.value,period:this.period.value,offset:null});}
  setOpen(open){this.open=open;this.popover.hidden=!open;this.trigger.setAttribute('aria-expanded',String(open));}
  moveMonth(delta){const [y,m]=this.month.split('-').map(Number),d=new Date(Date.UTC(y,m-1+delta,1));this.month=d.toISOString().slice(0,7);this.draw();}
  draw(focusDate=null){
    const el=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node;};
    const [y,m]=this.month.split('-').map(Number),first=new Date(Date.UTC(y,m-1,1)),days=new Date(Date.UTC(y,m,0)).getUTCDate(),today=this.time.date(Date.now(),this.draft.timezone);
    this.monthLabel.textContent=new Intl.DateTimeFormat('en-US',{month:'long',year:'numeric',timeZone:'UTC'}).format(first);this.previous.disabled=this.month<=today.slice(0,7);this.grid.replaceChildren();
    const headers=el('div');headers.setAttribute('role','row');for(const day of ['Su','Mo','Tu','We','Th','Fr','Sa']){const label=el('span',day);label.setAttribute('role','columnheader');headers.append(label);}this.grid.append(headers);
    let row;const selectedInMonth=this.draft.date.startsWith(this.month),focus=focusDate||(selectedInMonth?this.draft.date:today.startsWith(this.month)?today:this.month+'-01');
    for(let cell=0;cell<Math.ceil((first.getUTCDay()+days)/7)*7;cell++){
      if(cell%7===0){row=el('div');row.setAttribute('role','row');this.grid.append(row);}
      const day=cell-first.getUTCDay()+1;if(day<1||day>days){const blank=el('span');blank.setAttribute('role','gridcell');row.append(blank);continue;}
      const date=`${this.month}-${String(day).padStart(2,'0')}`,b=el('button',String(day));b.type='button';b.dataset.date=date;b.setAttribute('role','gridcell');b.setAttribute('aria-label',new Intl.DateTimeFormat('en-US',{dateStyle:'full',timeZone:'UTC'}).format(new Date(Date.UTC(y,m-1,day))));b.setAttribute('aria-selected',String(date===this.draft.date));if(date===today)b.setAttribute('aria-current','date');b.disabled=date<today;b.tabIndex=date===focus?0:-1;
      b.onclick=()=>{this.draft.date=date;this.draft.offset=null;this.draw(date);this.validate();this.grid.querySelector(`[data-date="${date}"]`)?.focus();};
      b.onkeydown=event=>{let delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7,Home:-new Date(date+'T12:00:00Z').getUTCDay(),End:6-new Date(date+'T12:00:00Z').getUTCDay()}[event.key];if(delta===undefined&&!['PageUp','PageDown'].includes(event.key))return;event.preventDefault();event.stopPropagation();const next=new Date(date+'T12:00:00Z');if(delta!==undefined)next.setUTCDate(next.getUTCDate()+delta);else{const target=new Date(Date.UTC(next.getUTCFullYear(),next.getUTCMonth()+(event.key==='PageUp'?-1:1),1));target.setUTCDate(Math.min(day,new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth()+1,0)).getUTCDate()));next.setTime(target.getTime());}const value=next.toISOString().slice(0,10);if(value<today)return;this.month=value.slice(0,7);this.draw(value);this.grid.querySelector(`[data-date="${value}"]`)?.focus();};row.append(b);
    }
    if(focusDate)this.grid.querySelector(`[data-date="${focusDate}"]`)?.focus();
  }
  validate(notify=true){
    const d=this.draft,h=Number(d.hour)%12+(d.period==='PM'?12:0),wall=`${d.date}T${String(h).padStart(2,'0')}:${d.minute}`,today=this.time.date(Date.now(),d.timezone);let error='',candidates=[];
    if(d.date<today)this.dateError.textContent='Choose today or a future date.';else this.dateError.textContent='';
    try{candidates=this.time.candidates(wall,d.timezone);}catch{error='Choose a valid timezone.';}
    this.repeatLabel.hidden=candidates.length<2;
    if(candidates.length===0)error ||= 'This time does not exist when the clocks change. Choose another time.';
    if(candidates.length>1){this.repeat.replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose which occurrence';this.repeat.append(placeholder);for(const [i,c] of candidates.entries()){const option=document.createElement('option');option.value=String(c.offset);option.textContent=`${i===0?'First':'Second'} occurrence (UTC${c.offset<0?'−':'+'}${String(Math.floor(Math.abs(c.offset)/60)).padStart(2,'0')}:${String(Math.abs(c.offset)%60).padStart(2,'0')})`;this.repeat.append(option);}this.repeat.value=d.offset==null?'':String(d.offset);if(d.offset==null)error='This hour occurs twice. Choose the first or second occurrence.';}
    const selected=candidates.find(c=>c.offset===d.offset)||(candidates.length===1?candidates[0]:null);
    if(selected&&selected.instant<Date.now()+30*60000)error='Choose a time at least 30 minutes from now. Long videos may need more time.';
    this.value=selected&&!error&&!this.dateError.textContent?{local_datetime:wall,timezone:d.timezone,utc_offset_minutes:selected.offset}:null;
    this.timeError.textContent=error;this.valid=!!this.value;this.summary.textContent=this.valid?'Selected time: '+this.time.format(this.value)+'.':this.dateError.textContent||error;
    for(const input of [this.hour,this.minute,this.period])input.setAttribute('aria-invalid',String(!!error));
    if(notify)this.onChange?.();return this.valid;
  }
  load(schedule){if(!schedule)return;const [date,time]=schedule.local_datetime.split('T'),[hour,minute]=time.split(':').map(Number);Object.assign(this.draft,{date,hour:String(hour%12||12),minute:String(minute).padStart(2,'0'),period:hour<12?'AM':'PM',timezone:schedule.timezone,offset:schedule.utc_offset_minutes});this.month=date.slice(0,7);this.hour.value=this.draft.hour;this.minute.value=this.draft.minute;this.period.value=this.draft.period;if(![...this.zone.options].some(option=>option.value===this.draft.timezone)){const option=document.createElement('option');option.value=option.textContent=this.draft.timezone;this.zone.append(option);}this.zone.value=this.draft.timezone;this.draw();this.validate(false);}
};
