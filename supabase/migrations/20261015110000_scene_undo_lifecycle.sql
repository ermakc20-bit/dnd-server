-- Scene creation undo keeps original identity/history in campaign trash.
alter table app.scenes add column deleted_at timestamptz;
create index scenes_active_campaign_idx on app.scenes(campaign_id,created_at,id)
where deleted_at is null;

create function app.guard_active_scene_reference() returns trigger
language plpgsql set search_path=app,pg_temp as $$
declare scene uuid;
begin
  scene := case when TG_TABLE_NAME='scenes' then (to_jsonb(NEW)->>'id')::uuid
                when TG_TABLE_NAME='rooms' then (to_jsonb(NEW)->>'active_scene_id')::uuid
                else (to_jsonb(NEW)->>'scene_id')::uuid end;
  if exists(select 1 from app.scenes where id=scene and deleted_at is not null) and
     (exists(select 1 from app.rooms where active_scene_id=scene)
      or exists(select 1 from app.scene_items where scene_id=scene and deleted_at is null)
      or exists(select 1 from app.scene_annotations where scene_id=scene and deleted_at is null)
      or exists(select 1 from app.ability_presentations where scene_id=scene)) then
    raise exception 'Deleted scene is still referenced' using errcode='23514';
  end if;
  return null;
end;
$$;
create constraint trigger scenes_active_reference after update on app.scenes
 deferrable initially deferred for each row execute function app.guard_active_scene_reference();
create constraint trigger rooms_active_scene_reference after insert or update on app.rooms
 deferrable initially deferred for each row execute function app.guard_active_scene_reference();
create constraint trigger scene_items_active_scene_reference after insert or update on app.scene_items
 deferrable initially deferred for each row execute function app.guard_active_scene_reference();
create constraint trigger scene_annotations_active_scene_reference after insert or update on app.scene_annotations
 deferrable initially deferred for each row execute function app.guard_active_scene_reference();
create constraint trigger presentations_active_scene_reference after insert or update on app.ability_presentations
 deferrable initially deferred for each row execute function app.guard_active_scene_reference();
revoke all on function app.guard_active_scene_reference() from public,anon,authenticated;
