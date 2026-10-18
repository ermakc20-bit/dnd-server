-- Campaign trash is durable; no history, card identity, or existing visibility is rewritten.
alter table app.cards add column deleted_at timestamptz;
alter table app.scene_items add column deleted_at timestamptz;
create index cards_active_room_idx on app.cards(room_id,created_at,id) where deleted_at is null;
create index scene_items_active_scene_idx on app.scene_items(scene_id,z_index,id) where deleted_at is null;

-- A deleted token may keep its original card reference for restoration. Active
-- representations must point to an active card, including at transaction commit.
create function app.check_active_card_reference() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_table_name = 'cards' then
    if exists(select 1 from app.cards c join app.scene_items i on i.card_id=c.id
              where c.id=new.id and c.deleted_at is not null and i.deleted_at is null) then
      raise exception 'card_in_use' using errcode='23514';
    end if;
  elsif exists(select 1 from app.scene_items i join app.cards c on c.id=i.card_id
               where i.id=new.id and i.deleted_at is null and c.deleted_at is not null) then
    raise exception 'card_unavailable' using errcode='23514';
  end if;
  return null;
end;
$$;
revoke all on function app.check_active_card_reference() from public,anon,authenticated;
create constraint trigger cards_active_reference after update on app.cards
  deferrable initially deferred for each row execute function app.check_active_card_reference();
create constraint trigger scene_items_active_card_reference after insert or update on app.scene_items
  deferrable initially deferred for each row execute function app.check_active_card_reference();
