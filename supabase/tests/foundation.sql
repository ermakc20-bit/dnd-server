begin;

create extension if not exists pgtap with schema extensions;

select plan(13);

select has_schema('app', 'private application schema exists');
select has_table('app', 'profiles', 'profiles table exists');
select has_table('app', 'rooms', 'rooms table exists');
select has_table('app', 'scenes', 'scenes table exists');
select has_table('app', 'scene_items', 'scene_items table exists');
select has_table('app', 'room_events', 'durable room events table exists');
select has_function(
  'app',
  'create_profile_for_new_user',
  array[]::text[],
  'new auth users receive an application profile'
);

select is(
  (
    select count(*)::bigint
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'app'
      and relation.relkind = 'r'
      and relation.relrowsecurity
  ),
  11::bigint,
  'RLS is enabled on every application table'
);

select ok(
  not has_schema_privilege('anon', 'app', 'usage'),
  'anon cannot access the private application schema'
);
select ok(
  not has_schema_privilege('authenticated', 'app', 'usage'),
  'authenticated cannot access the private application schema'
);
select ok(
  exists (
    select 1
    from storage.buckets
    where id = 'vtt-assets'
      and not public
      and file_size_limit = 52428800
  ),
  'private VTT asset bucket exists with the expected size limit'
);

insert into auth.users (id, email, raw_user_meta_data)
values (
  '10000000-0000-4000-8000-000000000001',
  'foundation-test@example.invalid',
  '{"display_name": "Test GM"}'::jsonb
);

select ok(
  exists (
    select 1
    from app.profiles
    where user_id = '10000000-0000-4000-8000-000000000001'
      and display_name = 'Test GM'
  ),
  'auth user trigger creates the expected profile'
);
select is(
  (
    select role::text
    from app.profiles
    where user_id = '10000000-0000-4000-8000-000000000001'
  ),
  'player',
  'new users cannot self-select an elevated role'
);

select * from finish();

rollback;
