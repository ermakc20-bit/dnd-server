begin;
create extension if not exists pgtap with schema extensions;
select plan(8);
select has_column('app','scenes','deleted_at','scene trash retains identity');
select has_index('app','scenes','scenes_active_campaign_idx','active scene reader index');
select ok(not has_table_privilege('authenticated','app.scenes','update'),'browser cannot mutate scenes');
insert into auth.users(id,email) values('f5100000-0000-4000-8000-000000000001','f5-schema@example.invalid');
insert into app.campaigns(id,owner_user_id,name) values
('f5100000-0000-4000-8000-000000000002','f5100000-0000-4000-8000-000000000001','F5');
insert into app.rooms(id,campaign_id,owner_user_id,name) values
('f5100000-0000-4000-8000-000000000003','f5100000-0000-4000-8000-000000000002','f5100000-0000-4000-8000-000000000001','F5');
insert into app.scenes(id,room_id,campaign_id,name,deleted_at) values
('f5100000-0000-4000-8000-000000000004','f5100000-0000-4000-8000-000000000003','f5100000-0000-4000-8000-000000000002','Trash',now()),
('f5100000-0000-4000-8000-000000000005','f5100000-0000-4000-8000-000000000003','f5100000-0000-4000-8000-000000000002','Active',null);
set constraints all immediate;
select throws_ok($$update app.rooms set active_scene_id='f5100000-0000-4000-8000-000000000004'
where id='f5100000-0000-4000-8000-000000000003'$$,'23514',null,'deleted scene cannot become active');
select throws_ok($$insert into app.scene_items(scene_id,campaign_id,kind)
values('f5100000-0000-4000-8000-000000000004','f5100000-0000-4000-8000-000000000002','token')$$,
'23514',null,'deleted scene cannot receive a live token');
select lives_ok($$update app.rooms set active_scene_id='f5100000-0000-4000-8000-000000000005'
where id='f5100000-0000-4000-8000-000000000003'$$,'active scene remains usable');
select throws_ok($$update app.scenes set deleted_at=now() where id='f5100000-0000-4000-8000-000000000005'$$,
'23514',null,'active pointer blocks trash');
select lives_ok($$update app.rooms set active_scene_id=null where id='f5100000-0000-4000-8000-000000000003';
update app.scenes set deleted_at=now() where id='f5100000-0000-4000-8000-000000000005'$$,
'cleared pointer permits empty scene trash');
select * from finish();
rollback;
