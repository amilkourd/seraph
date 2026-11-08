-- Addresses can be moved off a building (re-addressed building, old test address): log that action too.
alter table public.registry_access_log drop constraint if exists registry_access_log_action_check;
alter table public.registry_access_log add constraint registry_access_log_action_check
  check (action in ('lookup', 'get_model', 'register', 'add_address', 'remove_address'));
