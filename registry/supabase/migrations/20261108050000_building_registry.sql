-- Seraph building registry on Supabase (Postgres + Storage).
-- Everything is prefixed `registry_` (shared project) and closed to clients: RLS on, no policy, privileges revoked
-- from anon/authenticated. Only the server-side secret key (service_role) reads and writes, through
-- registry/building_registry/backends/supabase.py.

-- Buildings: one row per building model, keyed by a stable national id (RNB) or a manual id for test buildings.
create table if not exists public.registry_buildings (
  building_id   text primary key
                check (building_id ~ '^([0-9A-Z]{12}|[a-z0-9][a-z0-9-]{2,62})$'),
  id_kind       text not null check (id_kind in ('rnb', 'manual')),
  name          text not null,
  provenance    text not null check (provenance in ('architect', 'rebuilt_from_posted_plan', 'fictional')),
  provenance_fr text not null,
  exercise      boolean not null default false,          -- « exercice »: test/demo entry, never a real intervention
  rnb_ids       text[] not null default '{}',            -- every RNB building this model covers
  model         jsonb not null,                          -- extractor + version, hashes, stats, checks, file list
  registered_at timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  check (id_kind <> 'rnb' or building_id ~ '^[0-9A-Z]{12}$')
);
create index if not exists registry_buildings_rnb_ids_idx on public.registry_buildings using gin (rnb_ids);

-- Addresses: normalized keys (offline exact match) and BAN ids (online match). One key → one building.
create table if not exists public.registry_addresses (
  key         text primary key,                          -- building_registry.address.normalize(label)
  building_id text not null references public.registry_buildings (building_id) on delete cascade,
  label       text not null,
  source      text not null check (source in ('ban', 'manual', 'cache')),
  ban_id      text,                                      -- BAN cle_interop, e.g. 75109_6358_00009
  ban_uuid    uuid,
  lat         double precision,
  lon         double precision,
  created_at  timestamptz not null default now()
);
create index if not exists registry_addresses_building_idx on public.registry_addresses (building_id);
create index if not exists registry_addresses_ban_idx on public.registry_addresses (ban_id);

-- Access log: who read which building, when, for which incident. Append-only; outlives the buildings it names.
create table if not exists public.registry_access_log (
  id          bigint generated always as identity primary key,
  at          timestamptz not null default now(),
  actor       text not null,
  action      text not null check (action in ('lookup', 'get_model', 'register', 'add_address')),
  result      text not null check (result in ('hit', 'miss', 'ok', 'error')),
  building_id text,
  incident_id text,
  query       text
);
create index if not exists registry_access_log_building_idx on public.registry_access_log (building_id, at desc);
create index if not exists registry_access_log_incident_idx on public.registry_access_log (incident_id, at desc);

-- Closed to every client key.
alter table public.registry_buildings  enable row level security;
alter table public.registry_addresses  enable row level security;
alter table public.registry_access_log enable row level security;
revoke all on public.registry_buildings, public.registry_addresses, public.registry_access_log
  from anon, authenticated;

-- The log cannot be rewritten, not even with the secret key through the API.
revoke update, delete on public.registry_access_log from service_role;

-- Files: private bucket, no storage policy → only the secret key reads or writes.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('building-models', 'building-models', false, 52428800,
        array['application/json', 'image/svg+xml', 'text/plain', 'text/yaml', 'application/x-step',
              'application/octet-stream'])
on conflict (id) do nothing;
