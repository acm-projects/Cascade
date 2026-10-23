const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise initialization with a small DOM stub; media rendering is independent
// of which clips are included and deliberately fails in this fixture.
class Element {
  constructor() {
    this.children=[];this.dataset={};this.style={setProperty(){}};
    this.classList={add(){},remove(){},toggle(){}};
  }
  append(...children) { this.children.push(...children);for(const child of children)child.parentElement=this; }
  setAttribute() {}
  addEventListener() {}
  pause() {}
  scrollTo() {}
}
const a='a'.repeat(32), b='b'.repeat(32);
const entry=(job_id,clip_index)=>({job_id,clip_index});
async function initialize(selected,search='') {
  const elements=new Map();let navigation;
  const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context={
    URLSearchParams,location:{search},localStorage:{getItem:()=>null},
    clearTimeout(){},setTimeout(){},matchMedia:()=>({matches:true}),
    document:{getElementById:element,createElement:()=>new Element(),
      createTextNode:text=>({textContent:text}),querySelector:element,
      querySelectorAll:()=>[],addEventListener(){}},
    getComputedStyle:()=>({columnGap:'20'}),
    ResizeObserver:class {observe(){}},
    requestAnimationFrame(){},
    window:{CascadeExportSelection:{read:()=>selected},
      CascadeClipNavigation:class {constructor(options){navigation=options;} active(){}},
      addEventListener(){}},
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/exports_C.js'),'utf8'),context);
  await context.window.CascadeExports.initialize({project:{id:'project'},userId:'user',setStatus(){},
    apiJSON:async url=>{
      if(url.endsWith('/editor'))return {sessions:[
        {session_id:'first',session_number:1,wave_id:'save-a',wave_number:1,job_id:a,clips:[{},{}]},
        {session_id:'second',session_number:2,wave_id:'save-b',wave_number:1,job_id:b,clips:[{},{},{}]},
      ]};
      throw Error('Media rendering excluded from selection fixture');
    },
  });
  return {elements,navigation};
}
(async()=>{
  const {elements,navigation}=await initialize([entry(b,2),entry(a,1)]);
  const tiles=elements.get('export-deck').children;
  assert.equal(tiles.length,1,'Selections across sessions must share one tile');
  assert.equal(navigation.items.length,2,'Unselected clips must be excluded');
  assert.deepEqual(Array.from(navigation.items,row=>row.key),[b+':2',a+':1']);
  assert.equal(navigation.items[0].group,navigation.items[1].group);
  assert.equal(navigation.items[0].group.rows.length,2);
  assert.equal(navigation.items[0].group.download.textContent,'Download clips (2)');
  for(const selection of [[],[entry('c'.repeat(32),0)]]) {
    const result=await initialize(selection);
    assert.equal(result.elements.get('export-deck').children.length,0);
    assert.match(result.elements.get('export-deck').textContent,/No selected clips/);
    assert.equal(result.navigation,undefined);
  }
  const direct=await initialize([],'?job='+a+'&clip=1');
  assert.equal(direct.navigation.items.length,1);
  assert.equal(direct.navigation.items[0].key,a+':1');
  console.log('PASS: one tile across sessions, selected subset/order, empty/unavailable selections, direct clip link');
})().catch(error=>{console.error(error);process.exitCode=1;});
