/* F3 native authority/privacy acceptance, synthetic loopback only. */
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {randomUUID}=require('node:crypto');
const {chromium}=require(process.env.VTT_PLAYWRIGHT_MODULE);
const base=process.env.VTT_E2E_URL, output=process.env.VTT_E2E_OUTPUT;
assert.equal(new URL(base).hostname,'127.0.0.1');
const connected=page=>page.getByText(/Последняя синхронизация:.*Связь установлена/).waitFor({timeout:15000});
const until=async(page,check)=>{for(let i=0;i<150;i++){if(await check())return;await page.waitForTimeout(100);}throw new Error('public readback timeout');};
let stage='launch';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.VTT_CHROME_EXECUTABLE,headless:true});
 const errors=[];
 try {
  const gmContext=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});
  const guestContext=await browser.newContext({viewport:{width:1280,height:900}});
  const gm=await gmContext.newPage(); gm.on('pageerror',error=>errors.push(error.name));
  const token=(await (await gm.request.get(base+'/__e2e/bootstrap')).json()).token;
  const headers={Authorization:'Bearer '+token};
  stage='native campaign';await gm.goto(base);
  await gm.getByRole('button',{name:'Создать кампанию',exact:true}).click();
  await gm.getByLabel('Название кампании',{exact:true}).fill('F3 native owned');
  await gm.getByRole('button',{name:'Сохранить кампанию',exact:true}).click();await connected(gm);
  const room=new URL(gm.url()).pathname.split('/').pop();const route='/api/v1/rooms/'+room;
  const projection=async()=>{const r=await gm.request.get(base+route+'/scene',{headers});assert.equal(r.status(),200);return r.json();};
  const status=async()=>{const r=await gm.request.get(base+route+'/participants/status',{headers});assert.equal(r.status(),200);return (await r.json()).participants;};
  const journal=async()=>{const r=await gm.request.get(base+route+'/security-events?limit=100',{headers});assert.equal(r.status(),200);return (await r.json()).events;};
  stage='native scene/map';await gm.getByLabel('Название сцены',{exact:true}).fill('F3 map');
  await gm.getByRole('button',{name:'Создать сцену',exact:true}).click();await until(gm,async()=>!!(await projection()).scene);
  await gm.getByLabel('Файл изображения',{exact:true}).setInputFiles(path.join(output,'ready-map.png'));
  await gm.getByRole('button',{name:'Загрузить изображение',exact:true}).click();await until(gm,async()=>(await projection()).items.some(i=>i.kind==='map'));
  await gm.getByRole('button',{name:'Создать простой токен',exact:true}).click();
  await until(gm,async()=>(await projection()).items.some(i=>i.kind==='token'));
  const visible=(await projection()).items.find(i=>i.kind==='token');
  stage='actual guest join';await gm.getByRole('button',{name:'Участники',exact:true}).click();
  await gm.getByRole('button',{name:'Выпустить приглашение',exact:true}).click();
  const link=await gm.locator('output.invite-link').textContent();const guest=await guestContext.newPage();
  guest.on('pageerror',error=>errors.push(error.name));await guest.goto(link);
  await guest.getByLabel('Ваше имя',{exact:true}).fill('F3 guest');
  await guest.getByRole('button',{name:'Войти в комнату',exact:true}).click();await connected(guest);
  const guestRow=(await status()).find(p=>p.role==='player');assert.ok(guestRow);
  await gm.getByRole('button',{name:'Сцена',exact:true}).click();
  await gm.getByLabel(/^Выбранный объект/).selectOption(visible.id);
  await gm.getByRole('button',{name:'Загрузить игроков',exact:true}).click();
  await gm.getByLabel(/^Управление токеном/).selectOption({label:'F3 guest'});
  await gm.getByLabel('Название объекта',{exact:true}).fill('F3 assigned token');
  await gm.getByRole('button',{name:'Сохранить трансформацию',exact:true}).click();
  await until(gm,async()=>(await status()).find(p=>p.id===guestRow.id).assigned_tokens.some(i=>i.name==='F3 assigned token'));
  // The hidden canary uses the same public server command authority.
  const beforeHidden=await projection();
  const hiddenResponse=await gm.request.post(base+route+'/scene/commands',{headers,data:{
   command_id:randomUUID(),room_id:room,actor_session_id:beforeHidden.actor_session_id,
   expected_aggregate_version:beforeHidden.aggregate_version,type:'item.create',
   payload:{kind:'token',name:'GM_PRIVATE_CANARY',visibility:'gm_only'},client_sent_at:new Date().toISOString()}});
  assert.equal((await hiddenResponse.json()).status,'accepted');
  await until(gm,async()=>(await projection()).items.some(i=>i.name==='GM_PRIVATE_CANARY'));
  await gm.getByRole('button',{name:'Участники',exact:true}).click();
  await gm.getByRole('button',{name:'Показать участников',exact:true}).click();
  await gm.getByText('F3 assigned token · F3 map',{exact:true}).waitFor();
  await gm.getByRole('button',{name:'Журнал безопасности',exact:true}).click();
  await gm.getByText(/Вход в комнату · F3 guest/).waitFor();
  stage='socket dedup native';const second=await guestContext.newPage();await second.goto(link);await connected(second);
  assert.equal((await status()).filter(p=>p.id===guestRow.id).length,1);
  await second.close();await until(gm,async()=>(await journal()).some(e=>e.type==='connection.closed'&&e.reason==='socket_closed_actor_connected'));
  assert.equal((await status()).find(p=>p.id===guestRow.id).connection_status,'connected');
  const denied=await guest.request.get(base+route+'/security-events');assert.equal(denied.status(),403);
  assert.equal((await guest.request.get(base+route+'/participants/status')).status(),403);
  assert.equal((await guest.locator('body').textContent()).includes('GM_PRIVATE_CANARY'),false);
  assert.equal(await guest.getByRole('button',{name:'Журнал безопасности',exact:true}).count(),0);
  stage='signed links inside confirmed allowed text';
  const signedUrl='https://e.invalid/map(1).png?X-Amz-Signature=F3_SIGNED_CANARY';
  const unsignedUrl="https://public.invalid/map(1)'one';v=2,part@box+name.png";
  async function confirmedCommand(type,payload) {
   const current=await projection();const response=await gm.request.post(base+route+'/scene/commands',{headers,data:{
    command_id:randomUUID(),room_id:room,actor_session_id:current.actor_session_id,
    expected_aggregate_version:current.aggregate_version,type,payload,client_sent_at:new Date().toISOString()}});
   assert.equal((await response.json()).status,'accepted');
  }
  const textScene=await projection();
  await confirmedCommand('scene.rename',{scene_id:textScene.scene.id,name:`F3 map ${signedUrl}`});
  await confirmedCommand('annotation.create',{kind:'label',points:[{x:32,y:64}],
   label:`Обычный текст 1234 ${unsignedUrl} ${signedUrl}`,visibility:'gm_only'});
  stage='32 second true browser outage';await gm.getByRole('button',{name:'Сцена',exact:true}).click();
  const before=await projection();await gm.getByText(new RegExp(`Версия ${before.aggregate_version} ·`)).waitFor();
  const snapshotMetadata={version:before.aggregate_version,cursor:before.event_cursor,items:before.items.length};
  let nonTicketRequests=0;const track=request=>{if(request.url().includes('/api/')&&!request.url().includes('/realtime/ticket'))nonTicketRequests++;};
  const start=Date.now();await Promise.all([gmContext.setOffline(true),guestContext.setOffline(true)]);
  await gm.getByText('Только чтение · последнее подтверждённое состояние',{exact:true}).waitFor();
  await gm.waitForTimeout(32000);
  assert.ok(Date.now()-start>=32000);
  await gm.getByRole('button',{name:'Скачать аварийный снимок',exact:true}).waitFor();
  assert.equal(await guest.getByRole('button',{name:'Скачать аварийный снимок',exact:true}).count(),0);
  assert.ok(await gm.getByRole('button',{name:'Создать простой токен',exact:true}).isDisabled());
  gm.on('request',track);
  const [download]=await Promise.all([gm.waitForEvent('download'),gm.getByRole('button',{name:'Скачать аварийный снимок',exact:true}).click()]);
  await download.saveAs(path.join(output,'confirmed-local.json'));gm.off('request',track);
  const raw=fs.readFileSync(path.join(output,'confirmed-local.json'),'utf8'),local=JSON.parse(raw);
  assert.equal(local.schema_version,1);assert.equal(local.room_id,room);
  assert.equal(local.aggregate_version,snapshotMetadata.version);assert.equal(local.event_cursor,snapshotMetadata.cursor);
  assert.equal(local.items.length,snapshotMetadata.items);assert.ok(local.confirmed_at);
  for(const forbidden of ['actor_session_id','guest_session_id','authorization','signed_url','invite_token','pendingCommand'])assert.equal(raw.includes(forbidden),false);
  assert.equal(raw.includes(token),false);assert.equal(nonTicketRequests,0);
  assert.equal(raw.includes('F3_SIGNED_CANARY'),false);assert.equal(raw.includes(signedUrl),false);
  assert.equal(local.scene.name.includes('F3 map'),true);
  assert.equal(local.scenes.some(scene=>scene.name.includes('F3_SIGNED_CANARY')),false);
  assert.ok(local.annotations.some(annotation=>annotation.label.includes('Обычный текст 1234')&&annotation.label.includes(unsignedUrl)));
  assert.deepEqual(local.annotations.find(annotation=>annotation.label.includes('Обычный текст 1234')).points,[{x:32,y:64}]);
  assert.equal((await projection()).scene.name.includes('F3_SIGNED_CANARY'),true);
  await gm.screenshot({path:path.join(output,'gm-offline-32s.png')});
  await guest.screenshot({path:path.join(output,'guest-offline-32s.png')});
  const offlineSeconds=(Date.now()-start)/1000;
  stage='reconnect and journal readback';await Promise.all([gmContext.setOffline(false),guestContext.setOffline(false)]);
  await Promise.all([connected(gm),connected(guest)]);
  assert.equal(await gm.getByRole('button',{name:'Скачать аварийный снимок',exact:true}).count(),0);
  assert.equal((await projection()).aggregate_version,snapshotMetadata.version);
  await until(gm,async()=>(await status()).find(p=>p.id===guestRow.id).connection_status==='connected');
  const currentJournal=await journal();assert.ok(currentJournal.some(e=>e.participant_id===guestRow.id&&e.type==='connection.closed'));
  assert.ok(currentJournal.filter(e=>e.participant_id===guestRow.id&&e.type==='connection.opened').length>=3);
  stage='guest close and restore';await guest.close();await until(gm,async()=>(await status()).find(p=>p.id===guestRow.id).connection_status==='disconnected');
  const restored=await guestContext.newPage();await restored.goto(link);await connected(restored);
  assert.equal((await journal()).filter(e=>e.type==='participant.joined').length,1);
  // The download left authority data unchanged. Remove only the synthetic
  // signed-link fixture through online commands before the existing ZIP control.
  stage='clear signed-link fixture after download readback';
  const signedFixture=await projection();const mark=signedFixture.annotations.find(annotation=>annotation.label.includes('F3_SIGNED_CANARY'));
  assert.ok(mark);await confirmedCommand('scene.rename',{scene_id:signedFixture.scene.id,name:'F3 map'});
  await confirmedCommand('annotation.update',{annotation_id:mark.id,annotation:{kind:'label',points:[{x:32,y:64}],
   label:`Обычный текст 1234 ${unsignedUrl}`,visibility:'gm_only'}});
  const clearedFixture=await projection();assert.equal(clearedFixture.scene.name,'F3 map');
  assert.equal(clearedFixture.annotations.some(annotation=>annotation.label.includes('F3_SIGNED_CANARY')),false);
  assert.equal(clearedFixture.annotations.find(annotation=>annotation.id===mark.id).label,`Обычный текст 1234 ${unsignedUrl}`);
  stage='security isolated from archive';const campaign=beforeHidden.scene? (await (await gm.request.get(base+'/api/v1/campaigns',{headers})).json())[0].id:null;
  const job=randomUUID();const exportResponse=await gm.request.post(base+'/api/v1/campaign-transfers/'+job+'/export',
   {headers,data:{campaign_id:campaign,include_history:true,include_snapshot:true}});assert.equal(exportResponse.status(),202);
  await until(gm,async()=>{const r=await gm.request.get(base+'/api/v1/campaign-transfers/'+job,{headers});return (await r.json()).phase==='completed';});
  const archive=await gm.request.get(base+'/api/v1/campaign-transfers/'+job+'/archive',{headers});assert.equal(archive.status(),200);
  fs.writeFileSync(path.join(output,'campaign.zip'),await archive.body());
  stage='revoke native clear';await gm.request.delete(base+route+'/participants/'+guestRow.id,{headers});
  await restored.getByText('Доступ к комнате отозван',{exact:true}).waitFor({timeout:10000});
  assert.equal(await restored.getByRole('region',{name:'Игровая сцена',exact:true}).count(),0);
  assert.equal(await restored.getByRole('button',{name:'Скачать аварийный снимок',exact:true}).count(),0);
  assert.equal(errors.length,0);
  fs.writeFileSync(path.join(output,'room-security-results.json'),JSON.stringify({status:'passed',
   viewport:'1280x900',offline_seconds:offlineSeconds,download_extra_requests:nonTicketRequests,
   confirmed_snapshot:snapshotMetadata,guest_private_canary_visible:false,actor_socket_dedup:true,
   actual_guest_joins:1,observed_security_events:currentJournal.length,journal_guest_status:403,
   known_signed_download_canary_absent:true,ordinary_text_unsigned_url_preserved:true,
   authority_text_unchanged_by_download:true,
   reconnect_confirmed:true,revoke_cleared:true,browser_errors:errors.length},null,2));
 } catch(error){fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({stage,error:error.name,operation:error.message.split('\n')[0].replace(/https?:\/\/\S+/g,'[redacted-url]'),frames:(error.stack||'').split('\n').filter(line=>line.includes('room-security.cjs:')).slice(0,2)}));throw new Error('Native F3 failed: '+stage+' ('+error.name+')');}
 finally{await browser.close();}
})().catch(()=>{process.exitCode=1;});
