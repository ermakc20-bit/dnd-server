alter table app.scenes add column campaign_id uuid;
update app.scenes s set campaign_id = r.campaign_id from app.rooms r where s.room_id = r.id;
alter table app.scenes
  alter column campaign_id set not null,
  add constraint scenes_campaign_fkey foreign key (campaign_id)
    references app.campaigns(id) on delete cascade,
  add constraint scenes_id_campaign_unique unique (id, campaign_id),
  add column unit_size double precision not null default 5 check (unit_size > 0 and unit_size <= 10000),
  add column unit_label text not null default 'фут' check (char_length(unit_label) between 1 and 24),
  add column snap_enabled boolean not null default true;
alter table app.rooms
  drop constraint rooms_active_scene_belongs_to_room,
  add constraint rooms_active_scene_belongs_to_campaign
    foreign key (active_scene_id, campaign_id) references app.scenes(id, campaign_id),
  add column scene_version bigint not null default 0 check (scene_version >= 0);
alter table app.participants add constraint participants_id_campaign_unique unique(id, campaign_id);

alter table app.assets
  add column campaign_id uuid references app.campaigns(id) on delete cascade,
  add column uploaded_by uuid references app.participants(id) on delete set null,
  add column status text not null default 'pending' check (status in ('pending', 'ready')),
  add constraint assets_image_mime check (
    content_type in ('image/jpeg', 'image/png', 'image/webp', 'image/avif')
  ) not valid,
  add constraint assets_id_campaign_unique unique (id, campaign_id);
alter table app.scene_items
  add column campaign_id uuid,
  add column owner_participant_id uuid,
  add column created_by_participant_id uuid,
  alter column created_by drop not null;
update app.scene_items i set campaign_id = s.campaign_id from app.scenes s where i.scene_id = s.id;
-- Foundation assets were owner-scoped and could be shared by unrelated rooms.
-- Preserve every reference as campaign-owned pending metadata, without copying
-- or publishing Storage objects during migration. Additional campaigns retain
-- the original source key only as internal migration metadata until re-upload.
do $$
declare
  association record;
  new_asset_id uuid;
begin
  for association in
    select distinct asset_id, campaign_id from app.scene_items
    where asset_id is not null order by asset_id, campaign_id
  loop
    if (select campaign_id is null from app.assets where id=association.asset_id) then
      update app.assets set campaign_id=association.campaign_id where id=association.asset_id;
    elsif (select campaign_id from app.assets where id=association.asset_id) <> association.campaign_id then
      new_asset_id := gen_random_uuid();
      insert into app.assets(id,owner_user_id,campaign_id,name,kind,object_key,content_type,
                             byte_size,width,height,metadata,created_at,updated_at)
      select new_asset_id,owner_user_id,association.campaign_id,name,kind,
             'legacy-pending/' || new_asset_id::text,content_type,byte_size,width,height,
             metadata || jsonb_build_object('legacy_asset_id',id,'legacy_object_key',object_key),
             created_at,updated_at
      from app.assets where id=association.asset_id;
      update app.scene_items set asset_id=new_asset_id
      where asset_id=association.asset_id and campaign_id=association.campaign_id;
    end if;
  end loop;
end;
$$;
alter table app.scene_items
  alter column campaign_id set not null,
  add constraint scene_items_scene_campaign_fkey foreign key(scene_id, campaign_id)
    references app.scenes(id, campaign_id) on delete cascade,
  add constraint scene_items_asset_campaign_fkey foreign key(asset_id, campaign_id)
    references app.assets(id, campaign_id) on delete set null (asset_id),
  add constraint scene_items_owner_campaign_fkey foreign key(owner_participant_id, campaign_id)
    references app.participants(id, campaign_id) on delete set null (owner_participant_id),
  add constraint scene_items_creator_campaign_fkey foreign key(created_by_participant_id, campaign_id)
    references app.participants(id, campaign_id) on delete set null (created_by_participant_id);
create index scenes_campaign_order_idx on app.scenes(campaign_id, created_at, id);
create index assets_campaign_order_idx on app.assets(campaign_id, created_at, id);

create table app.scene_commands (
  command_id uuid primary key,
  room_id uuid not null references app.rooms(id) on delete cascade,
  actor_participant_id uuid not null,
  payload_hash text not null,
  result jsonb not null check (jsonb_typeof(result) = 'object'),
  created_at timestamptz not null default now(),
  foreign key(actor_participant_id, room_id) references app.participants(id, room_id)
);
alter table app.scene_commands enable row level security;
revoke all on app.scene_commands from public, anon, authenticated;
alter table app.room_events add column command_id uuid unique references app.scene_commands(command_id);
-- Storage stays private; uploads and expiring downloads are server-authorized.
update storage.buckets set public=false, file_size_limit=52428800,
  allowed_mime_types=array['image/jpeg','image/png','image/webp','image/avif']
where id='vtt-assets';
