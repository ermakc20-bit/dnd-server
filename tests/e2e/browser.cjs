/* Mandatory native AppView acceptance. Explicit loopback synthetic fixture only. */
const fs=require('node:fs'); const path=require('node:path'); const assert=require('node:assert/strict');
const {chromium}=require(process.env.VTT_PLAYWRIGHT_MODULE || 'playwright');
const base=process.env.VTT_E2E_URL || 'http://127.0.0.1:5190'; const output=process.env.VTT_E2E_OUTPUT;
assert.ok(['localhost','127.0.0.1'].includes(new URL(base).hostname));
let stage='launch'; const errors=[]; let gmPage;
const connected=page=>page.getByLabel('Связь установлена',{exact:true}).waitFor({timeout:15000});
const until=async(page,check)=>{for(let index=0;index<150;index++){if(await check())return;await page.waitForTimeout(100);}throw new Error('Public read-back timeout');};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.VTT_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try {
  const gmContext=await browser.newContext({viewport:{width:1440,height:900}});
  const gm=await gmContext.newPage();gmPage=gm;gm.on('pageerror',error=>errors.push(error.name));
  const gmToken=(await (await gm.request.get(base+'/__e2e/bootstrap')).json()).token;
  const headers={Authorization:'Bearer '+gmToken};
  stage='native campaign';await gm.goto(base);
  await gm.getByRole('button',{name:'Создать кампанию',exact:true}).click();
  await gm.getByLabel('Название кампании',{exact:true}).fill('Synthetic native acceptance');
  await gm.getByRole('button',{name:'Сохранить кампанию',exact:true}).click();await connected(gm);
  const roomPath=new URL(gm.url()).pathname;const room=roomPath.split('/').pop();const route='/api/v1/rooms/'+room;
  const snapshot=async(page)=>{const response=await page.request.get(base+route+'/scene',page===gm?{headers}:{});assert.equal(response.status(),200);return response.json();};
  stage='map and template';
  await gm.getByRole('button',{name:'Сцена',exact:true}).click();
  await gm.getByLabel('Название сцены',{exact:true}).fill('Synthetic scene');
  await gm.getByRole('button',{name:'Создать сцену',exact:true}).click();await until(gm,async()=>!!(await snapshot(gm)).scene);
  await gm.getByLabel('Файл изображения',{exact:true}).setInputFiles(path.join(output,'ready-map.png'));
  await gm.getByRole('button',{name:'Загрузить изображение',exact:true}).click();
  await until(gm,async()=>(await snapshot(gm)).items.some(item=>item.kind==='map'));
  await until(gm,async()=>gm.locator('.scene-canvas').evaluate(host=>{const canvas=host.querySelector('canvas');return !!canvas&&canvas.width>0&&canvas.height>0&&Math.abs(canvas.width/devicePixelRatio-host.clientWidth)<2;}));
  await gm.getByRole('button',{name:'Импорт',exact:true}).click();
  await gm.getByLabel('Файл карточек',{exact:true}).setInputFiles(path.join(output,'filled-template.xlsx'));
  await gm.getByRole('button',{name:'Разобрать файл',exact:true}).click();
  await gm.getByRole('button',{name:'Подтвердить импорт (1)',exact:true}).click();
  await gm.getByRole('status').filter({hasText:'Импорт подтверждён'}).waitFor();
  await until(gm,async()=>(await snapshot(gm)).items.some(item=>item.card_id));
  const item=(await snapshot(gm)).items.find(item=>item.card_id);
  stage='guest and ownership';
  await gm.getByRole('button',{name:'Участники',exact:true}).click();
  await gm.getByRole('button',{name:'Выпустить приглашение',exact:true}).click();
  const invitation=gm.locator('output.invite-link');await invitation.waitFor();const joinUrl=await invitation.textContent();
  const playerContext=await browser.newContext({viewport:{width:1024,height:768},hasTouch:true});
  const player=await playerContext.newPage();player.on('pageerror',error=>errors.push(error.name));
  await playerContext.route('**/*',route=>['localhost','127.0.0.1'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
  await player.goto(joinUrl);await player.getByLabel('Ваше имя',{exact:true}).fill('Synthetic guest');
  await player.getByRole('button',{name:'Войти в комнату',exact:true}).click();await connected(player);
  await player.reload();await connected(player);
  assert.equal(await player.getByRole('button',{name:'Создать сцену',exact:true}).count(),0);
  await gm.getByRole('button',{name:'Карточки',exact:true}).click();
  await gm.getByRole('button',{name:/Герой теста/}).click();
  await gm.getByRole('button',{name:'Редактировать карточку',exact:true}).click();
  await gm.getByText('Игровой пакет и доступ',{exact:true}).click();
  await gm.getByRole('button',{name:'Обновить участников',exact:true}).click();
  await gm.getByLabel(/^Назначить карточку/).selectOption({label:'Synthetic guest'});
  await gm.getByRole('button',{name:'Сохранить карточку',exact:true}).click();
  await gm.getByRole('button',{name:'Сцена',exact:true}).click();
  await gm.getByLabel(/^Выбранный объект/).selectOption(item.id);
  await gm.getByRole('button',{name:'Загрузить игроков',exact:true}).click();
  await gm.getByLabel(/^Управление токеном/).selectOption({label:'Synthetic guest'});
  await gm.getByLabel('X',{exact:true}).fill('128');await gm.getByLabel('Y',{exact:true}).fill('128');
  await gm.getByRole('button',{name:'Сохранить трансформацию',exact:true}).click();
  await until(player,async()=>(await snapshot(player)).items.some(entry=>entry.id===item.id&&entry.can_transform&&entry.x===128));
  stage='authorized native token control'; let tokenCommands=0;
  player.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/scene/commands')&&request.postDataJSON()?.type==='item.update')tokenCommands++;});
  await player.getByRole('button',{name:'Сцена',exact:true}).tap();
  await player.getByLabel(/^Выбранный объект/).selectOption(item.id);
  await until(player,async()=>!(await player.getByRole('button',{name:'Сохранить трансформацию',exact:true}).isDisabled()));
  await player.getByLabel('X',{exact:true}).fill('192');
  await player.getByRole('button',{name:'Сохранить трансформацию',exact:true}).tap();
  await until(player,async()=>(await snapshot(player)).items.find(entry=>entry.id===item.id).x===192);
  assert.equal(tokenCommands,1); assert.equal((await snapshot(gm)).items.find(entry=>entry.id===item.id).x,192);
  stage='resource and geometry'; let geometryCommands=0;
  player.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/scene/commands')&&request.postDataJSON()?.type==='ability.present')geometryCommands++;});
  await player.getByRole('button',{name:'Карточки',exact:true}).tap();await player.getByRole('button',{name:/Герой теста/}).tap();
  await player.getByLabel('Текущее: HP',{exact:true}).fill('7');await player.getByRole('button',{name:'Сохранить HP',exact:true}).tap();
  const cards=async(page,r=room)=>{const response=await page.request.get(base+`/api/v1/rooms/${r}/cards`,page===gm?{headers}:{});assert.equal(response.status(),200);return response.json();};
  await until(player,async()=>(await cards(player)).cards[0].resources[0].current===7);
  await player.getByRole('button',{name:'Показать область: Сфера',exact:true}).tap();
  const surface=player.getByRole('region',{name:'Карта и токены',exact:true});await surface.scrollIntoViewIfNeeded();
  const box=await surface.boundingBox();await player.touchscreen.tap(box.x+256,box.y+180);
  assert.equal(geometryCommands,0);
  await player.getByRole('button',{name:'Показать способность',exact:true}).tap();
  await until(player,async()=>(await snapshot(player)).ability_presentations.length===1);
  assert.equal(geometryCommands,1); const beforeTransfer=await snapshot(gm);assert.equal(beforeTransfer.ability_presentations.length,1);
  stage='offline and automatic resync';
  await player.getByRole('button',{name:'Карточки',exact:true}).tap();
  await playerContext.setOffline(true);await player.getByRole('status').filter({hasText:'Только чтение'}).waitFor();
  assert.equal(await player.getByRole('button',{name:'Сохранить HP',exact:true}).isDisabled(),true);
  assert.equal(await player.locator('.scene-canvas canvas').count(),1);
  await gm.getByLabel('X',{exact:true}).fill('256');
  await gm.getByRole('button',{name:'Сохранить трансформацию',exact:true}).click();
  await until(gm,async()=>(await snapshot(gm)).items.find(entry=>entry.id===item.id).x===256);
  await playerContext.setOffline(false);await connected(player);
  await until(player,async()=>(await snapshot(player)).items.find(entry=>entry.id===item.id).x===256);
  await until(player,async()=>!(await player.getByRole('button',{name:'Сохранить HP',exact:true}).isDisabled()));
  assert.equal((await cards(player)).cards[0].resources[0].current,7);
  stage='native export and import';
  await gm.getByRole('button',{name:'К кампаниям',exact:true}).click();
  await gm.getByText('Настройки и перенос',{exact:true}).first().click();
  const exportPanel=gm.getByRole('region',{name:'Экспорт кампании',exact:true}).first();
  await exportPanel.getByRole('button',{name:'Экспорт кампании',exact:true}).click();
  await exportPanel.getByLabel('Добавить последние 1000 событий',{exact:true}).check();
  await exportPanel.getByLabel('Добавить подтверждённый снимок',{exact:true}).check();
  await exportPanel.getByRole('button',{name:'Подготовить ZIP',exact:true}).click();
  const downloaded=gm.waitForEvent('download');await exportPanel.getByRole('button',{name:'Скачать ZIP',exact:true}).click();
  const archive=path.join(output,'roundtrip.zip');await(await downloaded).saveAs(archive);
  const importPanel=gm.getByRole('region',{name:'Импортировать кампанию',exact:true});
  await importPanel.getByRole('button',{name:'Импортировать кампанию',exact:true}).click();
  await importPanel.getByLabel('ZIP кампании',{exact:true}).setInputFiles(archive);
  await importPanel.getByRole('button',{name:'Восстановить независимую кампанию',exact:true}).click();
  await importPanel.getByRole('status').filter({hasText:'Создана независимая кампания'}).waitFor({timeout:15000});
  const campaigns=await(await gm.request.get(base+'/api/v1/campaigns',{headers})).json();assert.equal(campaigns.length,2);
  const restoredRoom=campaigns.flatMap(campaign=>campaign.rooms).find(entry=>entry.id!==room);assert.ok(restoredRoom);
  const restored=await(await gm.request.get(base+`/api/v1/rooms/${restoredRoom.id}/scene`,{headers})).json();
  assert.notEqual(restored.scene.id,beforeTransfer.scene.id);assert.equal(restored.items.length,beforeTransfer.items.length);
  assert.equal(restored.items.find(entry=>entry.kind==='token').x,256);
  assert.deepEqual(restored.ability_presentations[0].geometry,beforeTransfer.ability_presentations[0].geometry);
  const restoredCard=(await cards(gm,restoredRoom.id)).cards[0];assert.equal(restoredCard.resources[0].current,7);assert.notEqual(restoredCard.id,item.card_id);
  const raster=restored.items.find(entry=>entry.kind==='map');
  const grant=await(await gm.request.get(base+`/api/v1/rooms/${restoredRoom.id}/assets/${raster.asset_id}/download`,{headers})).json();
  stage='restored raster bytes'; const restoredImage=await(await gm.request.get(base+grant.url)).body();assert.deepEqual(restoredImage,fs.readFileSync(path.join(output,'ready-map.png')));
  await gm.goto(base+`/rooms/${restoredRoom.id}`);await connected(gm);
  await until(gm,async()=>gm.locator('.scene-canvas canvas').evaluate(canvas=>canvas.width>0&&canvas.height>0));
  stage='F7 explicit ability launch from open card';
  const {randomUUID}=require('node:crypto');
  await gm.goto(base+roomPath);await connected(gm);
  const publicCommand=async(type,payload)=>{
   const state=await snapshot(gm);
   const response=await gm.request.post(base+route+'/scene/commands',{headers,data:{command_id:randomUUID(),room_id:room,
    actor_session_id:state.actor_session_id,expected_aggregate_version:state.aggregate_version,type,payload,client_sent_at:new Date().toISOString()}});
   assert.equal(response.status(),200);assert.equal((await response.json()).status,'accepted');
  };
  const f7Card=(await cards(gm)).cards.find(card=>card.id===item.card_id);assert.ok(f7Card);
  const {id,campaign_id,room_id,version,created_at,updated_at,can_edit_structure,can_edit_current,can_export,...cardData}=f7Card;
  const f7Abilities=['token','point'].flatMap(origin=>['circle','radius','cone','line','cube'].map(shape=>({
   id:randomUUID(),schema_version:1,name:`F7 ${origin} ${shape}`,description:'Synthetic launch acceptance',action_type:null,uses:null,automation:null,visibility:'everyone',
   geometry:{shape,origin,radius:10,length:10,width:5,angle:90,units:'фут',color:'#ff7448'}
  })));
  await publicCommand('card.update',{card_id:id,card:{...cardData,abilities:[...cardData.abilities,...f7Abilities]}});
  await publicCommand('item.create',{kind:'token',name:'F7 source B',card_id:id,owner_participant_id:f7Card.owner_participant_id,
   visibility:'everyone',x:384,y:128,width:64,height:64});
  const sources=(await snapshot(gm)).items.filter(entry=>entry.kind==='token'&&entry.card_id===id);
  assert.equal(sources.length,2);const chosen=sources.find(entry=>entry.name==='F7 source B');assert.ok(chosen);
  const sourceCoordinates=sources.map(entry=>({id:entry.id,x:entry.x,y:entry.y,width:entry.width,height:entry.height}));
  const touchPage=await playerContext.newPage();touchPage.on('pageerror',error=>errors.push(error.name));
  await touchPage.goto(player.url());await connected(touchPage);
  const f7Cases=[],f7MoveCases=[];
  for(const [page,touch] of [[gm,false],[touchPage,true]]) {
   const sent=[];const listener=request=>{if(request.method()==='POST'&&request.url().endsWith('/scene/commands'))sent.push(request.postDataJSON());};
   page.on('request',listener);
   const activate=async locator=>touch?locator.tap():locator.click();
   const openCard=async()=>{
    const cardsTab=page.getByRole('button',{name:'Карточки',exact:true});
    if(await cardsTab.getAttribute('aria-pressed')!=='true')await activate(cardsTab);
    if(!await page.getByRole('article',{name:'Карточка Герой теста',exact:true}).isVisible())
     await activate(page.locator('.card-list').getByRole('button',{name:/Герой теста/}));
   };
   const session=touch?await page.context().newCDPSession(page):null;
   const place=async(box,start,end)=>{
    if(touch) {
     await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+start.x,y:box.y+start.y}]});
     await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+end.x,y:box.y+end.y}]});
     await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    } else {
     await page.mouse.move(box.x+start.x,box.y+start.y);await page.mouse.down();
     await page.mouse.move(box.x+end.x,box.y+end.y,{steps:5});await page.mouse.up();
    }
   };
   for(const ability of f7Abilities) {
    stage=`F7 ${touch?'touch':'desktop'} ${ability.name}`;
    await openCard();let actions=0;const before=await snapshot(page),commandsBefore=sent.length;
    const token=ability.geometry.origin==='token',directed=['cone','line','cube'].includes(ability.geometry.shape);
    await activate(page.getByRole('button',{name:`Показать область: ${ability.name}${token?' · источник: F7 source B':''}`,exact:true}));actions++;
    const host=page.getByRole('region',{name:'Карта и токены',exact:true});await host.scrollIntoViewIfNeeded();const bounds=await host.boundingBox();assert.ok(bounds);
    const origin=token?{x:chosen.x+chosen.width/2,y:chosen.y+chosen.height/2}:{x:180,y:180},direction={x:560,y:220};
    if(!token) {await place(bounds,origin,directed?direction:origin);actions++;}
    else if(directed) {
     if(touch)await page.touchscreen.tap(bounds.x+direction.x,bounds.y+direction.y);
     else await page.mouse.click(bounds.x+direction.x,bounds.y+direction.y);
     actions++;
    }
    assert.equal(sent.length,commandsBefore);
    assert.equal(await host.locator('canvas').count(),1);
    if(ability.name==='F7 point cone')await page.screenshot({path:path.join(output,`f7-${touch?'touch':'desktop'}-preview.png`)});
    await activate(page.getByRole('button',{name:'Показать способность',exact:true}));actions++;
    await until(page,async()=>(await snapshot(page)).ability_presentations.some(area=>!before.ability_presentations.some(previous=>previous.id===area.id)));
    await page.getByRole('button',{name:'Показать способность',exact:true}).waitFor({state:'hidden'});
    assert.ok(actions<=3);assert.equal(sent.length,commandsBefore+1);
    const command=sent.at(-1);assert.equal(command.type,'ability.present');assert.equal(command.payload.ability_id,ability.id);
    if(token)assert.equal(command.payload.origin_item_id,chosen.id);else assert.equal('origin_item_id' in command.payload,false);
    const area=(await snapshot(page)).ability_presentations.find(entry=>!before.ability_presentations.some(previous=>previous.id===entry.id));
    assert.equal(area.geometry.shape,ability.geometry.shape);
    assert.ok(Math.abs(area.geometry.origin.x-origin.x)<0.01);assert.ok(Math.abs(area.geometry.origin.y-origin.y)<0.01);
    assert.ok(Math.abs(area.geometry.rotation-(directed?Math.atan2(direction.y-origin.y,direction.x-origin.x):0))<0.01);
    assert.deepEqual((await snapshot(gm)).items.filter(entry=>sources.some(source=>source.id===entry.id))
     .map(entry=>({id:entry.id,x:entry.x,y:entry.y,width:entry.width,height:entry.height})),sourceCoordinates);
    f7Cases.push({device:touch?'touch':'desktop',origin:ability.geometry.origin,shape:ability.geometry.shape,actions,
     commands_before_confirm:0,commands_after_confirm:1,public_geometry_readback:true,source_coordinates_unchanged:true});
   }
   // Place the second gesture on exposed canvas, clear of the bottom-left controls.
   for(const ability of f7Abilities.filter(entry=>entry.geometry.origin==='point')) {
    stage=`F7 ${touch?'touch':'desktop'} move draft ${ability.geometry.shape}`;
    await openCard();const before=await snapshot(page),commandsBefore=sent.length;
    await activate(page.getByRole('button',{name:`Показать область: ${ability.name}`,exact:true}));
    const host=page.getByRole('region',{name:'Карта и токены',exact:true});await host.scrollIntoViewIfNeeded();const bounds=await host.boundingBox();
    const directed=['cone','line','cube'].includes(ability.geometry.shape),finalOrigin={x:600,y:256},finalDirection={x:600,y:128};
    await place(bounds,{x:180,y:180},directed?{x:560,y:220}:{x:180,y:180});
    await place(bounds,finalOrigin,directed?finalDirection:finalOrigin);assert.equal(sent.length,commandsBefore);
    await activate(page.getByRole('button',{name:'Показать способность',exact:true}));
    await until(page,async()=>(await snapshot(page)).ability_presentations.some(area=>!before.ability_presentations.some(previous=>previous.id===area.id)));
    await page.getByRole('button',{name:'Показать способность',exact:true}).waitFor({state:'hidden'});
    assert.equal(sent.length,commandsBefore+1);assert.equal(sent.at(-1).type,'ability.present');
    const area=(await snapshot(page)).ability_presentations.find(entry=>!before.ability_presentations.some(previous=>previous.id===entry.id));
    assert.equal(area.geometry.shape,ability.geometry.shape);assert.ok(Math.abs(area.geometry.origin.x-finalOrigin.x)<0.01);
    assert.ok(Math.abs(area.geometry.origin.y-finalOrigin.y)<0.01);
    assert.ok(Math.abs(area.geometry.rotation-(directed?-Math.PI/2:0))<0.01);
    assert.deepEqual((await snapshot(gm)).items.filter(entry=>sources.some(source=>source.id===entry.id))
     .map(entry=>({id:entry.id,x:entry.x,y:entry.y,width:entry.width,height:entry.height})),sourceCoordinates);
    f7MoveCases.push({device:touch?'touch':'desktop',shape:ability.geometry.shape,optional_reposition_before_confirm:true,
     commands_before_confirm:0,commands_after_confirm:1,only_final_origin_B_persisted:true});
   }
   stage=`F7 ${touch?'touch':'desktop'} offline draft control`;
   await openCard();await activate(page.getByRole('button',{name:'Показать область: F7 point cone',exact:true}));
   const host=page.getByRole('region',{name:'Карта и токены',exact:true});await host.scrollIntoViewIfNeeded();const bounds=await host.boundingBox();
   await place(bounds,{x:180,y:180},{x:560,y:220});const commandsBefore=sent.length;
   await page.context().setOffline(true);await page.getByRole('status').filter({hasText:'Только чтение'}).waitFor();
   assert.equal(await host.locator('canvas').count(),1);
   assert.equal(await page.getByRole('button',{name:'Показать способность',exact:true}).count(),0);
   await page.context().setOffline(false);await connected(page);
   assert.equal(await page.getByRole('button',{name:'Показать способность',exact:true}).count(),0);assert.equal(sent.length,commandsBefore);
   page.off('request',listener);if(session)await session.detach();
  }
  assert.equal(f7Cases.length,20);
  assert.equal(f7MoveCases.length,10);
  fs.writeFileSync(path.join(output,'f7-ability-launch.json'),JSON.stringify({status:'passed',cases:f7Cases,move_cases:f7MoveCases,offline_drafts_cleared:['desktop','touch']},null,2));
  assert.deepEqual(errors,[]);
  const result={status:'passed',synthetic:true,browser_version:browser.version(),native_paths:['GM/guest restore','raster/template-confirm/token','assigned token controls','current HP','touch geometry','offline/read-only/resync','native ZIP/new IDs/raster bytes/resource/geometry'],page_errors:0,token_durable_commands:tokenCommands,geometry_durable_commands:geometryCommands,resource_current:7,placement_actions_after_selection:2,hosted_auth_storage:'not_verified',actual_games:0,real_twenty_minute_gate:'not_verified'};
  result.native_paths.push('F7 explicit source/point gesture/confirm desktop+touch');
  result.f7_ability_launch_cases=f7Cases.length;result.f7_maximum_launch_actions=Math.max(...f7Cases.map(entry=>entry.actions));
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 } catch(error) {
  if(gmPage&&!gmPage.isClosed())await gmPage.screenshot({path:path.join(output,'failure-desktop.png')}).catch(()=>{});
  throw error;
 } finally {await browser.close();}
})().catch(error=>{fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({status:'failed',kind:error.name,message:error.message,stage,at:error.stack?.split('\n').find(line=>line.includes('browser.cjs:'))?.trim(),page_errors:errors}));console.error('Native browser acceptance failed:',error.name,stage);process.exit(1);});
