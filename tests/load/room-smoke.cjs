/* Public HTTP/WS smoke. Loopback synthetic fixture only; no installed test dependency. */
const assert=require('node:assert/strict'); const fs=require('node:fs'); const path=require('node:path');
const base=process.env.VTT_E2E_URL || 'http://127.0.0.1:5190';
assert.ok(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function request(route, actor, method='GET', body) {
  const response=await fetch(base+route,{method,headers:{...actor.headers,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
  assert.ok(response.ok, `HTTP ${response.status}`); return response.json();
}
async function waitFor(check) { const start=performance.now(); while(!check()) {if(performance.now()-start>10000)throw new Error('convergence timeout');await sleep(10);} }
(async()=>{
 const token=(await (await fetch(base+'/__e2e/bootstrap')).json()).token;
 const results=[];
 for(const count of [6,10]) {
  const gm={headers:{Authorization:'Bearer '+token}, frames:[]};
  const campaign=await request('/api/v1/campaigns',gm,'POST',{name:'Synthetic load'});
  const room=campaign.rooms[0].id; const route='/api/v1/rooms/'+room;
  const first=await request(route+'/scene',gm);gm.session=first.actor_session_id;
  let version=first.aggregate_version;
  async function command(actor,type,payload,id=crypto.randomUUID(), expected=version) {
   const envelope={command_id:id,room_id:room,actor_session_id:actor.session,expected_aggregate_version:expected,type,payload,client_sent_at:new Date().toISOString()};
   const result=await request(route+'/scene/commands',actor,'POST',envelope);
   if(result.status==='accepted')version=result.aggregate_version;
   return {result,envelope};
  }
  await command(gm,'scene.create',{name:'Synthetic load'});
  const marker='private-canary-'+crypto.randomUUID();
  await command(gm,'item.create',{name:marker,visibility:'gm_only'});
  const invite=await request(route+'/invites',gm,'POST',{});
  const actors=[gm];
  for(let index=1;index<count;index++) {
   const joined=await fetch(base+'/api/v1/join/'+invite.token,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:'Synthetic participant '+index})});
   assert.equal(joined.status,200);
   const session=await joined.json(); const cookies=joined.headers.getSetCookie().map(value=>value.split(';')[0]).join('; ');
   actors.push({headers:{Cookie:cookies},session:session.participant.guest_session_id,participant:session.participant.id,frames:[]});
  }
  for(let index=0;index<count;index++) {
   await command(gm,'item.create',{name:'Visible '+index,x:index*64,y:128,owner_participant_id:actors[index].participant || gm.session});
   const snapshot=await request(route+'/scene',gm); actors[index].item=snapshot.items.find(item=>item.name==='Visible '+index).id;
  }
  async function connect(actor,cursor=0) {
   const ticket=await request(route+'/realtime/ticket',actor,'POST');
   const ws=new WebSocket(base.replace('http','ws')+route+'/realtime/ws');actor.ws=ws;
   actor.last=null;
   ws.onmessage=event=>{ const frame=JSON.parse(event.data); if(frame.type==='sync') { if(actor!==gm)assert.equal(JSON.stringify(frame).includes(marker),false);actor.last=frame;actor.frames.push(frame.snapshot.event_cursor); } };
   await new Promise((resolve,reject)=>{ws.onopen=()=>{ws.send(JSON.stringify({type:'subscribe',ticket:ticket.ticket,cursor}));resolve();};ws.onerror=reject;});
   await waitFor(()=>actor.last!==null);
  }
  await Promise.all(actors.map(actor=>connect(actor)));
  const samples=[];let accepted=0;let duplicates=0;
  for(let index=0;index<30;index++) {
   const actor=actors[index%count]; const before=version; const started=performance.now();
   const {result,envelope}=await command(actor,'item.update',{item_id:actor.item,x:200+index,y:128});
   assert.equal(result.status,'accepted');accepted++;
   const duplicate=await request(route+'/scene/commands',actor,'POST',envelope);assert.equal(duplicate.status,'duplicate');duplicates++;
   assert.equal(duplicate.aggregate_version,before+1);
   await waitFor(()=>actors.every(entry=>entry.last?.snapshot.aggregate_version===version));
   const cursors=actors.map(entry=>entry.last.snapshot.event_cursor);assert.equal(new Set(cursors).size,1);
   for(const entry of actors)assert.ok(entry.last.events.some(event=>event.cursor===result.event_cursor&&event.type==='scene.changed'));
   samples.push(performance.now()-started);
  }
  const reconnectActor=actors.at(-1);const cursor=reconnectActor.last.snapshot.event_cursor;
  reconnectActor.ws.close();await sleep(20);
  await command(gm,'item.update',{item_id:gm.item,x:500,y:128});
  const started=performance.now();await connect(reconnectActor,cursor);
  assert.equal(reconnectActor.last.snapshot.aggregate_version,version);
  assert.ok(reconnectActor.last.events.some(event=>event.cursor>cursor));
  const reconnectMs=performance.now()-started;
  // Thirty acknowledged mutations plus one reconnect mutation; snapshot version proves no duplicate application.
  assert.equal(version,2+count+31);
  for(const actor of actors){assert.ok(actor.frames.every((value,index)=>index===0||value>=actor.frames[index-1]));actor.ws.close();}
  samples.sort((a,b)=>a-b);
  results.push({participants:count,accepted_commands:accepted,duplicate_receipts:duplicates,converged_samples:samples.length,p95_ms:Math.round(samples[Math.ceil(.95*samples.length)-1]*100)/100,reconnect_ms:Math.round(reconnectMs*100)/100,private_canary_leaks:0,event_cursor_convergence:true,version_delta:31});
 }
 const output={status:'passed',synthetic:true,cases:results,scope:'loopback protocol smoke; not WAN SLO or real games'};
 fs.writeFileSync(path.join(process.env.VTT_E2E_OUTPUT,'load-results.json'),JSON.stringify(output,null,2));console.log(JSON.stringify(output));
})().catch(error=>{console.error('Load acceptance failed:',error.name);process.exit(1);});
