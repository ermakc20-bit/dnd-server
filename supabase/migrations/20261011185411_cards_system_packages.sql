-- Cards are campaign entities attached to one room's authority/version stream.
create table app.cards (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references app.campaigns(id) on delete cascade,
  room_id uuid not null,
  owner_participant_id uuid,
  image_asset_id uuid,
  data jsonb not null check (
    jsonb_typeof(data)='object' and coalesce(data->'schema_version'='1'::jsonb,false)
  ),
  version bigint not null default 1 check (version >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(id,campaign_id),
  unique(id,room_id),
  foreign key(room_id,campaign_id) references app.rooms(id,campaign_id) on delete cascade,
  foreign key(owner_participant_id,room_id) references app.participants(id,room_id),
  foreign key(image_asset_id,campaign_id) references app.assets(id,campaign_id)
);
create index cards_room_order_idx on app.cards(room_id,created_at,id);
create index cards_owner_idx on app.cards(owner_participant_id);
create index cards_image_idx on app.cards(image_asset_id);
alter table app.cards enable row level security;
revoke all on app.cards from public, anon, authenticated;
alter table app.scene_items add column card_id uuid,
  add constraint scene_items_card_campaign_fkey foreign key(card_id,campaign_id)
    references app.cards(id,campaign_id),
  add constraint scene_items_card_token_only check (card_id is null or kind='token');
create index scene_items_card_idx on app.scene_items(card_id);
