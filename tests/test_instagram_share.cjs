/* Capability profiles, not real browsers/devices or Instagram automation. */
const assert=require('node:assert/strict');const {File}=require('node:buffer');
global.window={};require('../web/export_post.js');const sharing=window.CascadeInstagramShare;
(async()=>{
 const blob=new Blob(['final MP4 with saved edits/caption pixels/reframing/B-roll'],{type:'application/octet-stream'});
 const desktop={isSecureContext:true,File,navigator:{}};
 assert.equal(sharing.available(desktop),false);assert.equal(sharing.prepare(blob,'clip.mp4',desktop),null);
 const calls=[];let inClick=false;
 const mobile={isSecureContext:true,File,navigator:{canShare:data=>data.files?.[0]?.type==='video/mp4',share:data=>{assert.ok(inClick,'share must be invoked synchronously during the click');calls.push(data);return Promise.resolve();}}};
 const file=sharing.prepare(blob,'cascade-session-1-wave-2-clip-3.mp4',mobile);
 assert.equal(file.name,'cascade-session-1-wave-2-clip-3.mp4');assert.equal(file.type,'video/mp4');assert.equal(await file.text(),await blob.text());
 inClick=true;const sent=sharing.share(file,'Post caption\n\n#Cascade',mobile);inClick=false;await sent;
 assert.equal(calls[0].files[0],file);assert.equal(calls[0].text,'Post caption\n\n#Cascade');assert.equal(calls[0].url,undefined);
 // Text+file not supported: keep the video and leave manual caption copying available.
 mobile.navigator.canShare=data=>!('text' in data);inClick=true;await sharing.share(file,'caption',mobile);inClick=false;
 assert.equal(calls[1].text,undefined);assert.equal(calls[1].files[0],file);
 assert.equal(sharing.prepare(blob,'clip.mp4',{...mobile,isSecureContext:false}),null);
 assert.equal(sharing.prepare(blob,'clip.mp4',{...mobile,navigator:{canShare:()=>false,share(){throw Error('must not share');}}}),null);
 assert.equal(sharing.prepare(blob,'clip.mp4',{...mobile,navigator:{canShare(){throw Error('blocked policy');},share(){}}}),null);
 mobile.navigator.share=()=>Promise.reject(Object.assign(new Error('canceled'),{name:'AbortError'}));
 await assert.rejects(sharing.share(file,'',mobile),{name:'AbortError'});
 assert.match(sharing.message({name:'AbortError'}),/canceled or no share target/);assert.doesNotMatch(sharing.message({name:'AbortError'}),/published|attached/);
 assert.match(sharing.message({name:'NotAllowedError'}),/blocked/);assert.match(sharing.message({name:'DataError'}),/Could not share/);
 // Manual flow reserves a tab before awaiting the renderer; blocked popups still download.
 let downloaded=0;const order=[],popup={opener:{},closed:false,location:{href:''},close(){this.closed=true;}};
 const fallback=await sharing.downloadAndOpen({open:url=>{assert.equal(url,'about:blank');order.push('open');return popup;},download:async()=>{order.push('render/download');downloaded++;assert.equal(popup.location.href,'');}});
 assert.deepEqual(order,['open','render/download']);assert.equal(popup.opener,null);assert.equal(popup.location.href,'https://www.instagram.com/');assert.ok(fallback.ready);assert.match(fallback.message,/Click Create and select your downloaded clip\./);
 const blocked=await sharing.downloadAndOpen({open:()=>null,download:async()=>downloaded++});assert.equal(downloaded,2);assert.match(blocked.message,/popup was blocked/);
 const throwing=await sharing.downloadAndOpen({open:()=>{throw Error('blocked');},download:async()=>downloaded++});assert.equal(downloaded,3);assert.ok(throwing.ready);
 popup.closed=false;popup.location.href='';await assert.rejects(sharing.downloadAndOpen({open:()=>popup,download:async()=>{throw Error('Render failed');}}),/Render failed/);assert.ok(popup.closed);assert.equal(popup.location.href,'');
 console.log('PASS: mocked desktop/mobile capability profiles, final file bytes/name/MIME, caption payload and file-only fallback, synchronous share call, cancellation/errors, popup blocking and failed rendering. No physical device or Instagram app tested.');
})().catch(error=>{console.error(error);process.exitCode=1;});
