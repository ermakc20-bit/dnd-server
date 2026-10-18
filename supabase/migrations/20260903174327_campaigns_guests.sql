create type app.campaign_status as enum ('draft', 'active', 'archived');
create type app.participant_role as enum ('player', 'gm');

create table app.campaigns (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references app.profiles(user_id),
  name text not null check (char_length(name) between 1 and 120),
  system_id text not null default 'neutral' check (system_id ~ '^[a-z][a-z0-9_-]{1,31}$'),
  status app.campaign_status not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table app.rooms
  add column campaign_id uuid,
  add column is_locked boolean not null default false,
  add column pin_hash text;

-- The foundation model treated a room as the durable campaign. Give every
-- existing room a campaign with the same identifier so all foreign keys remain stable.
insert into app.campaigns (id, owner_user_id, name, system_id, status, created_at, updated_at)
select id, owner_user_id, name, game_system, 'active', created_at, updated_at
from app.rooms;

update app.rooms set campaign_id = id where campaign_id is null;

alter table app.rooms
  alter column campaign_id set not null,
  add constraint rooms_campaign_id_fkey
    foreign key (campaign_id) references app.campaigns(id) on delete cascade,
  add constraint rooms_id_campaign_unique unique (id, campaign_id);

create index rooms_campaign_created_idx on app.rooms (campaign_id, created_at);

create table app.participants (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references app.campaigns(id) on delete cascade,
  room_id uuid not null references app.rooms(id) on delete cascade,
  user_id uuid references app.profiles(user_id) on delete cascade,
  identity_kind text not null default 'registered'
    check (identity_kind in ('registered', 'guest')),
  role app.participant_role not null default 'player',
  permissions jsonb not null default '{}'::jsonb check (jsonb_typeof(permissions) = 'object'),
  display_name text not null check (char_length(display_name) between 1 and 80),
  joined_at timestamptz not null default now(),
  removed_at timestamptz,
  constraint participants_identity_valid check (
    (identity_kind = 'registered' and user_id is not null)
    or (identity_kind = 'guest' and user_id is null)
  ),
  constraint participants_room_campaign_unique unique (id, room_id)
);

alter table app.participants
  add constraint participants_room_belongs_to_campaign_fkey
    foreign key (room_id, campaign_id)
    references app.rooms (id, campaign_id)
    on delete cascade;

create unique index participants_registered_room_unique
  on app.participants (room_id, user_id)
  where user_id is not null;
create index participants_campaign_active_idx
  on app.participants (campaign_id, room_id)
  where removed_at is null;

insert into app.participants
  (campaign_id, room_id, user_id, identity_kind, role, display_name, joined_at)
select r.campaign_id, r.id, r.owner_user_id, 'registered', 'gm', p.display_name, r.created_at
from app.rooms r
join app.profiles p on p.user_id = r.owner_user_id;

insert into app.participants
  (campaign_id, room_id, user_id, identity_kind, role, display_name, joined_at)
select r.campaign_id, m.room_id, m.user_id, 'registered', m.role::text::app.participant_role,
       p.display_name, m.joined_at
from app.room_members m
join app.rooms r on r.id = m.room_id
join app.profiles p on p.user_id = m.user_id
on conflict (room_id, user_id) where user_id is not null do nothing;

-- Preserve historical actors without granting membership absent from room_members.
-- Existing owners and current members were inserted above and win on conflict.
insert into app.participants
  (campaign_id, room_id, user_id, identity_kind, role, display_name, joined_at, removed_at)
select distinct r.campaign_id, e.room_id, e.actor_user_id, 'registered',
       'player'::app.participant_role,
       p.display_name, e.created_at, now()
from app.room_events e
join app.rooms r on r.id = e.room_id
join app.profiles p on p.user_id = e.actor_user_id
on conflict (room_id, user_id) where user_id is not null do nothing;

create table app.guest_sessions (
  id uuid primary key,
  participant_id uuid not null unique references app.participants(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  constraint guest_sessions_expiry_after_creation check (expires_at > created_at)
);

alter table app.room_join_tokens
  add column failed_pin_attempts integer not null default 0
    check (failed_pin_attempts between 0 and 5),
  add column locked_until timestamptz;

create index guest_sessions_active_hash_idx
  on app.guest_sessions (token_hash, expires_at)
  where revoked_at is null;

alter table app.room_events
  add column actor_participant_id uuid;

update app.room_events e
set actor_participant_id = p.id
from app.participants p
where p.room_id = e.room_id and p.user_id = e.actor_user_id;

alter table app.room_events
  alter column actor_participant_id set not null,
  alter column actor_user_id drop not null,
  add constraint room_events_actor_participant_room_fkey
    foreign key (actor_participant_id, room_id)
    references app.participants (id, room_id),
  add constraint room_events_actor_identity_present check (
    actor_participant_id is not null
  );

create trigger campaigns_set_updated_at
before update on app.campaigns
for each row execute function app.set_updated_at();

alter table app.campaigns enable row level security;
alter table app.participants enable row level security;
alter table app.guest_sessions enable row level security;

revoke all on app.campaigns, app.participants, app.guest_sessions
  from public, anon, authenticated;

alter default privileges in schema app revoke all on tables from public, anon, authenticated;
alter default privileges in schema app revoke all on sequences from public, anon, authenticated;
alter default privileges in schema app revoke all on functions from public, anon, authenticated;
