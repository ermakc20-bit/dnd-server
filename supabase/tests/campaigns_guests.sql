begin;

create extension if not exists pgtap with schema extensions;

select plan(17);

select has_table('app', 'campaigns', 'campaigns are durable entities');
select has_table('app', 'participants', 'participants unify registered and guest actors');
select has_table('app', 'guest_sessions', 'guest refresh sessions are durable and revocable');
select has_column('app', 'rooms', 'campaign_id', 'rooms belong to campaigns');
select has_column('app', 'room_events', 'actor_participant_id', 'events identify a participant');
select has_column('app', 'room_join_tokens', 'failed_pin_attempts', 'PIN failures are counted');
select has_column('app', 'room_join_tokens', 'locked_until', 'PIN lockout has an expiry');

select ok(
  (select relrowsecurity from pg_class where oid = 'app.campaigns'::regclass),
  'campaigns have RLS defense in depth'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'app.participants'::regclass),
  'participants have RLS defense in depth'
);
select ok(
  not has_table_privilege('anon', 'app.campaigns', 'select'),
  'anon cannot read campaigns through the Data API'
);
select ok(
  not has_table_privilege('authenticated', 'app.participants', 'insert'),
  'authenticated clients cannot write gameplay membership directly'
);

insert into auth.users (id, email, raw_user_meta_data)
values (
  '31000000-0000-4000-8000-000000000001',
  'campaign-owner@example.invalid',
  '{"display_name": "Campaign Owner", "role": "admin"}'::jsonb
);

insert into app.campaigns (id, owner_user_id, name)
values (
  '31000000-0000-4000-8000-000000000002',
  '31000000-0000-4000-8000-000000000001',
  'Туманы Баровии'
);

insert into app.rooms (id, campaign_id, owner_user_id, name)
values (
  '31000000-0000-4000-8000-000000000003',
  '31000000-0000-4000-8000-000000000002',
  '31000000-0000-4000-8000-000000000001',
  'Основной стол'
);

insert into app.participants
  (id, campaign_id, room_id, user_id, identity_kind, role, display_name)
values (
  '31000000-0000-4000-8000-000000000004',
  '31000000-0000-4000-8000-000000000002',
  '31000000-0000-4000-8000-000000000003',
  '31000000-0000-4000-8000-000000000001',
  'registered',
  'gm',
  'Campaign Owner'
), (
  '31000000-0000-4000-8000-000000000005',
  '31000000-0000-4000-8000-000000000002',
  '31000000-0000-4000-8000-000000000003',
  null,
  'guest',
  'player',
  'Гость'
);

insert into app.guest_sessions
  (id, participant_id, token_hash, expires_at)
values (
  '31000000-0000-4000-8000-000000000006',
  '31000000-0000-4000-8000-000000000005',
  encode(extensions.digest('guest-secret', 'sha256'), 'hex'),
  now() + interval '12 hours'
);

select is(
  (select role::text from app.participants where user_id = '31000000-0000-4000-8000-000000000001'),
  'gm',
  'server-owned participant role is independent of user metadata'
);
select is(
  (select identity_kind from app.participants where id = '31000000-0000-4000-8000-000000000005'),
  'guest',
  'guest participant does not require a fake auth user'
);
select isnt(
  (select token_hash from app.guest_sessions where id = '31000000-0000-4000-8000-000000000006'),
  'guest-secret',
  'guest session stores a one-way token hash'
);

insert into app.room_events
  (room_id, actor_participant_id, actor_user_id, event_type, payload)
values (
  '31000000-0000-4000-8000-000000000003',
  '31000000-0000-4000-8000-000000000005',
  null,
  'participant.joined',
  '{}'::jsonb
);

select is(
  (select count(*)::bigint from app.room_events where actor_user_id is null),
  1::bigint,
  'guest participant can author a room event without auth.users'
);
select throws_ok(
  $$
    insert into app.participants
      (campaign_id, room_id, user_id, identity_kind, role, display_name)
    values (
      '31000000-0000-4000-8000-000000000002',
      '31000000-0000-4000-8000-000000000003',
      null,
      'registered',
      'gm',
      'Forged GM'
    )
  $$,
  '23514',
  null,
  'registered role cannot be forged without a registered identity'
);

insert into app.campaigns (id, owner_user_id, name)
values (
  '31000000-0000-4000-8000-000000000009',
  '31000000-0000-4000-8000-000000000001',
  'Другая кампания'
);

insert into auth.users (id, email, raw_user_meta_data)
values (
  '31000000-0000-4000-8000-000000000010',
  'wrong-campaign@example.invalid',
  '{"display_name": "Wrong campaign player"}'::jsonb
);

select throws_ok(
  $$
    insert into app.participants
      (campaign_id, room_id, user_id, identity_kind, role, display_name)
    values (
      '31000000-0000-4000-8000-000000000009',
      '31000000-0000-4000-8000-000000000003',
      '31000000-0000-4000-8000-000000000010',
      'registered',
      'player',
      'Wrong campaign'
    )
  $$,
  '23503',
  null,
  'participant room must belong to the same campaign'
);

select * from finish();

rollback;
