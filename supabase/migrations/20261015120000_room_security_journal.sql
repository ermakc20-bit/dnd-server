-- Runtime room security audit is private and never advances gameplay cursors.
create table app.room_security_events (
  id bigint generated always as identity primary key,
  room_id uuid not null references app.rooms(id) on delete cascade,
  participant_id uuid not null,
  display_name text not null check (char_length(display_name) between 1 and 80),
  type text not null check (type in ('participant.joined','connection.opened','connection.closed')),
  occurred_at timestamptz not null default clock_timestamp(),
  reason text not null,
  foreign key (participant_id,room_id) references app.participants(id,room_id) on delete cascade,
  constraint room_security_reason_matches_type check (
    (type='participant.joined' and reason in ('guest_join','registered_join')) or
    (type='connection.opened' and reason='authorized_socket') or
    (type='connection.closed' and reason in ('socket_closed_actor_connected',
      'socket_closed_actor_disconnected','socket_closed_actor_unknown'))
  )
);
create index room_security_events_page_idx on app.room_security_events(room_id,id desc);
alter table app.room_security_events enable row level security;
revoke all on app.room_security_events from public,anon,authenticated,service_role;
revoke all on sequence app.room_security_events_id_seq from public,anon,authenticated,service_role;
grant select,insert on app.room_security_events to service_role;
grant usage on sequence app.room_security_events_id_seq to service_role;
create policy room_security_service_read on app.room_security_events for select to service_role using (true);
create policy room_security_service_append on app.room_security_events for insert to service_role with check (true);
