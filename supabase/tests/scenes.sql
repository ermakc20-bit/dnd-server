begin;
create extension if not exists pgtap with schema extensions;
select plan(16);
select has_column('app','scenes','campaign_id','scene belongs to campaign');
select has_column('app','scenes','unit_size','calibration is durable');
select has_column('app','rooms','scene_version','room aggregate has a version');
select has_table('app','scene_commands','command receipts are durable');
select ok((select relrowsecurity from pg_class where oid='app.scene_commands'::regclass),'receipts have RLS');
select ok(not has_table_privilege('authenticated','app.scene_commands','insert'),'browser cannot write receipts');
select ok(not has_table_privilege('authenticated','app.scene_items','update'),'browser cannot write tokens');
select has_column('app','assets','status','asset failure preserves pending metadata');
select is((select public from storage.buckets where id='vtt-assets'),false,'bucket is private');
select is((select cardinality(allowed_mime_types) from storage.buckets where id='vtt-assets'),4,'four image formats');
select is((select file_size_limit from storage.buckets where id='vtt-assets'),52428800::bigint,'50 MiB limit');
insert into auth.users(id,email) values('42000000-0000-4000-8000-000000000001','scene-schema@example.invalid');
insert into app.campaigns(id,owner_user_id,name) values
('42000000-0000-4000-8000-000000000002','42000000-0000-4000-8000-000000000001','First'),
('42000000-0000-4000-8000-000000000003','42000000-0000-4000-8000-000000000001','Other');
insert into app.rooms(id,campaign_id,owner_user_id,name) values
('42000000-0000-4000-8000-000000000004','42000000-0000-4000-8000-000000000002','42000000-0000-4000-8000-000000000001','First'),
('42000000-0000-4000-8000-000000000005','42000000-0000-4000-8000-000000000003','42000000-0000-4000-8000-000000000001','Other'),
('42000000-0000-4000-8000-000000000006','42000000-0000-4000-8000-000000000002','42000000-0000-4000-8000-000000000001','Same campaign');
insert into app.scenes(id,campaign_id,room_id,name) values
('42000000-0000-4000-8000-000000000007','42000000-0000-4000-8000-000000000002','42000000-0000-4000-8000-000000000004','Scene');
select throws_ok($$update app.rooms set active_scene_id='42000000-0000-4000-8000-000000000007'
 where id='42000000-0000-4000-8000-000000000005'$$,'23503',null,'active scene cannot cross campaign');
select lives_ok($$update app.rooms set active_scene_id='42000000-0000-4000-8000-000000000007'
 where id='42000000-0000-4000-8000-000000000006'$$,'scene can be reused by room in same campaign');
insert into app.participants(id,campaign_id,room_id,identity_kind,display_name) values
('42000000-0000-4000-8000-000000000008','42000000-0000-4000-8000-000000000002','42000000-0000-4000-8000-000000000004','guest','Guest');
select lives_ok($$insert into app.scene_items(scene_id,campaign_id,kind,created_by_participant_id)
 values('42000000-0000-4000-8000-000000000007','42000000-0000-4000-8000-000000000002','token','42000000-0000-4000-8000-000000000008')$$,
 'guest can be token actor without fake profile');
insert into app.assets(id,campaign_id,owner_user_id,name,kind,object_key,content_type,byte_size) values
('42000000-0000-4000-8000-000000000009','42000000-0000-4000-8000-000000000003','42000000-0000-4000-8000-000000000001','Other asset','map','test/other','image/png',1);
select throws_ok($$insert into app.scene_items(scene_id,campaign_id,kind,asset_id)
 values('42000000-0000-4000-8000-000000000007','42000000-0000-4000-8000-000000000002','map','42000000-0000-4000-8000-000000000009')$$,
 '23503',null,'asset cannot cross campaign');
select throws_ok($$update app.scenes set unit_size=0 where id='42000000-0000-4000-8000-000000000007'$$,
 '23514',null,'calibration rejects zero');
select * from finish();
rollback;
