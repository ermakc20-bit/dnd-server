begin;
select plan(8);
select has_table('app','campaign_transfer_jobs','Transfer jobs exist');
select ok((select relrowsecurity from pg_class where oid='app.campaign_transfer_jobs'::regclass),
  'Transfer jobs require RLS');
select ok(not has_table_privilege('anon','app.campaign_transfer_jobs','SELECT'),
  'Anonymous cannot read private archives');
select ok(not has_table_privilege('authenticated','app.campaign_transfer_jobs','SELECT'),
  'Data API cannot read private archives');
select ok(not has_table_privilege('authenticated','app.campaign_transfer_jobs','INSERT,UPDATE,DELETE'),
  'Data API cannot mutate transfers');
select col_type_is('app','campaign_transfer_jobs','archive','bytea','Temporary archive bytes are durable');
select col_is_null('app','campaign_transfer_jobs','result_campaign_id','Receipt survives removed result');
select ok((select count(*)=2 from pg_constraint where conrelid='app.campaign_transfer_jobs'::regclass
  and contype='f' and confrelid='app.campaigns'::regclass and confdeltype='n'),
  'Removing source/result does not replay a completed job');
select * from finish();
rollback;
