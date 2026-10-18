begin;
create extension if not exists pgtap with schema extensions;
select plan(23);
select has_table('app','cards','native cards are durable');
select has_column('app','scene_items','card_id','tokens reference native cards');
select ok((select relrowsecurity from pg_class where oid='app.cards'::regclass),'cards have RLS');
select ok(not has_table_privilege(role_name,'app.cards',operation),role_name||' cannot '||operation)
from unnest(array['anon','authenticated']) as role_name
cross join unnest(array['SELECT','INSERT','UPDATE','DELETE']) as operation;
insert into auth.users(id,email) values('43000000-0000-4000-8000-000000000001','cards-schema@example.invalid');
insert into app.campaigns(id,owner_user_id,name) values
('43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000001','Cards');
insert into app.rooms(id,campaign_id,owner_user_id,name) values
('43000000-0000-4000-8000-000000000003','43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000001','Cards'),
('43000000-0000-4000-8000-000000000004','43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000001','Other');
select throws_ok($$insert into app.cards(campaign_id,room_id,data)
 values('43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000003','{}')$$,
 '23514',null,'schema version is mandatory');
select throws_ok($$insert into app.cards(campaign_id,room_id,data)
 values('43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000003','{"schema_version":2}')$$,
 '23514',null,'unsupported schema is rejected');
insert into app.participants(id,campaign_id,room_id,identity_kind,display_name) values
('43000000-0000-4000-8000-000000000005','43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000004','guest','Guest');
select throws_ok($$insert into app.cards(campaign_id,room_id,owner_participant_id,data)
 values('43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000003',
 '43000000-0000-4000-8000-000000000005','{"schema_version":1}')$$,
 '23503',null,'card assignment cannot cross rooms');
select ok(exists(select 1 from pg_constraint where conrelid='app.scene_items'::regclass
 and conname='scene_items_card_campaign_fkey'),'card token relation is campaign constrained');
select has_column('app','cards','deleted_at','card trash is durable');
select has_column('app','scene_items','deleted_at','token trash is durable');
insert into app.cards(id,campaign_id,room_id,data) values
('43000000-0000-4000-8000-000000000006','43000000-0000-4000-8000-000000000002',
 '43000000-0000-4000-8000-000000000003','{"schema_version":1,"name":"Character"}');
insert into app.scenes(id,campaign_id,room_id,name) values
('43000000-0000-4000-8000-000000000007','43000000-0000-4000-8000-000000000002',
 '43000000-0000-4000-8000-000000000003','Scene');
insert into app.scene_items(id,scene_id,campaign_id,card_id,kind,name) values
('43000000-0000-4000-8000-000000000008','43000000-0000-4000-8000-000000000007',
 '43000000-0000-4000-8000-000000000002','43000000-0000-4000-8000-000000000006','token','Token');
set constraints all immediate;
select throws_ok($$update app.cards set deleted_at=now() where id='43000000-0000-4000-8000-000000000006'$$,
 '23514','card_in_use','active token prevents card trash');
update app.scene_items set deleted_at=now() where id='43000000-0000-4000-8000-000000000008';
select is((select count(*)::integer from app.cards where id='43000000-0000-4000-8000-000000000006' and deleted_at is null),1,'token trash preserves library card');
select lives_ok($$update app.cards set deleted_at=now() where id='43000000-0000-4000-8000-000000000006'$$,'unused card can enter trash');
select throws_ok($$update app.scene_items set deleted_at=null where id='43000000-0000-4000-8000-000000000008'$$,
 '23514','card_unavailable','cannot restore token linked to card trash');
update app.cards set deleted_at=null where id='43000000-0000-4000-8000-000000000006';
select lives_ok($$update app.scene_items set deleted_at=null where id='43000000-0000-4000-8000-000000000008'$$,'restored card permits token restoration');
select lives_ok($$insert into app.scene_items(scene_id,campaign_id,card_id,kind,name) values
('43000000-0000-4000-8000-000000000007','43000000-0000-4000-8000-000000000002',
 '43000000-0000-4000-8000-000000000006','token','Second representation')$$,
 'multiple representations of one existing character are allowed');

select * from finish();
rollback;
