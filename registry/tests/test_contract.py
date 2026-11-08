"""One contract, every backend: what Seraph relies on, whatever registry is behind it.

Backends: local (a temp folder), supabase (the real backend code against an in-memory PostgREST + Storage),
supabase-live (the real project; only when SUPABASE_URL and a secret key are set), fire_service (read-only adapter
against a fake fire-service API). Registration runs the real IFC extractor on the fictional R+5.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from building_registry import ReadOnlyRegistry, RegistryError
from building_registry.backends.fire_service import FireServiceRegistry
from building_registry.backends.local import LocalRegistry
from building_registry.backends.supabase import SupabaseRegistry
from building_registry.config import env
from building_registry.ingest import copy_building, register

from fakes import FakeFireService, FakeSupabase

IFC_DIR = Path(__file__).resolve().parents[2] / "ifc"
ADDRESS = "1 rue de l'Exercice, 75009 Paris"
VARIANT = "1, Rue de l’EXERCICE — 75009 PARIS, France"
UNKNOWN = "10 rue de Rivoli, 75004 Paris"


@pytest.fixture(scope="session")
def dev_ifc(tmp_path_factory) -> Path:
    from seraph_ifc import author
    return author.build(IFC_DIR / "dev" / "trace.yaml", tmp_path_factory.mktemp("ifc") / "dev.ifc")


@pytest.fixture(scope="session")
def building_id() -> str:
    return f"test-r5-{uuid.uuid4().hex[:8]}"


def _live_supabase():
    if not env("SUPABASE_URL") or not (env("SUPABASE_SECRET_KEY") or env("SUPABASE_SERVICE_ROLE_KEY")):
        pytest.skip("live Supabase: set SUPABASE_URL and SUPABASE_SECRET_KEY to run it")
    return SupabaseRegistry(online=False)


@pytest.fixture(params=["local", "supabase", "supabase-live"])
def writable(request, tmp_path, dev_ifc, building_id):
    if request.param == "local":
        reg = LocalRegistry(root=tmp_path / "data", online=False)
    elif request.param == "supabase":
        reg = SupabaseRegistry(url="https://fake.supabase.co", key="sb_secret_test", online=False,
                               transport=FakeSupabase().transport)
    else:
        reg = _live_supabase()
    os.environ["REGISTRY_CACHE_DIR"] = str(tmp_path / "cache")
    r = register(reg, dev_ifc, [ADDRESS], building_id=building_id, exercise=True, online=False)
    assert r.status == "created"
    yield reg
    if request.param == "supabase-live":
        reg.delete(building_id)


def test_lookup_exact_variant_unknown(writable, building_id):
    rec = writable.lookup(ADDRESS, incident_id="INC-T1", actor="test")
    assert rec is not None and rec.building_id == building_id and rec.exercise
    assert writable.lookup(VARIANT, incident_id="INC-T1", actor="test").building_id == building_id
    assert writable.lookup(UNKNOWN, incident_id="INC-T1", actor="test") is None


def test_model_is_served_ready_for_seraph(writable, building_id):
    path = writable.model_path(building_id, incident_id="INC-T2", actor="test")
    b = json.loads(path.read_text(encoding="utf-8"))
    assert b["model"]["provenance"] == "fictional" and "graph" in b
    assert (path.parent / "levels" / "L3.svg").exists()
    assert writable.get_model(building_id, incident_id="INC-T2")["name"] == b["name"]


def test_access_log_says_who_read_what_for_which_incident(writable, building_id):
    writable.lookup(ADDRESS, incident_id="INC-T3", actor="seraph")
    writable.lookup(UNKNOWN, incident_id="INC-T3", actor="seraph")
    writable.model_path(building_id, incident_id="INC-T3", actor="seraph")
    log = writable.access_log(incident_id="INC-T3")
    seen = {(e.action, e.result, e.building_id) for e in log}
    assert ("lookup", "hit", building_id) in seen
    assert ("lookup", "miss", None) in seen
    assert ("get_model", "ok", building_id) in seen
    assert all(e.actor == "seraph" and e.at for e in log)


def test_register_is_idempotent_and_addresses_merge(writable, dev_ifc, building_id):
    again = register(writable, dev_ifc, [ADDRESS, "Bâtiment d'exercice, Paris"], building_id=building_id,
                     exercise=True, online=False)
    assert again.status == "unchanged"
    assert writable.lookup("Bâtiment d'exercice, Paris").building_id == building_id
    writable.add_address(building_id, "12 avenue du Test, 75001 Paris", online=False)
    writable.add_address(building_id, "12 avenue du Test, 75001 Paris", online=False)
    assert writable.lookup("12 av. du Test 75001 Paris").building_id == building_id
    assert building_id in [r.building_id for r in writable.list()]


def test_an_address_belongs_to_one_building(writable, dev_ifc, building_id):
    with pytest.raises(RegistryError):
        register(writable, dev_ifc, [ADDRESS], building_id=building_id + "-x", exercise=True, online=False)


def test_bad_ids_and_failed_checks_are_refused(writable, dev_ifc):
    with pytest.raises(RegistryError):
        register(writable, dev_ifc, ["99 rue Nulle, Paris"], building_id="Not An Id!", online=False)
    with pytest.raises(RegistryError):        # no RNB id offline and no manual id
        register(writable, dev_ifc, ["99 rue Nulle, Paris"], online=False)


# ───────── read-only: the fire service's own registry ─────────
@pytest.fixture
def fire_service(tmp_path, dev_ifc, building_id):
    src = LocalRegistry(root=tmp_path / "sdis", online=False)
    register(src, dev_ifc, [ADDRESS], building_id=building_id, exercise=True, online=False)
    os.environ["REGISTRY_CACHE_DIR"] = str(tmp_path / "cache")
    return FireServiceRegistry(url="https://sdis.example", token="test-token", online=False,
                               transport=FakeFireService(src).transport)


def test_fire_service_reads_through_the_same_interface(fire_service, building_id):
    rec = fire_service.lookup(VARIANT, incident_id="INC-T4", actor="seraph")
    assert rec is not None and rec.building_id == building_id
    assert fire_service.lookup(UNKNOWN) is None
    path = fire_service.model_path(building_id, incident_id="INC-T4")
    assert json.loads(path.read_text(encoding="utf-8"))["graph"]["nodes"]
    assert (path.parent / "levels" / "L0.svg").exists()
    assert {(e.action, e.result) for e in fire_service.access_log(incident_id="INC-T4")} >= {("lookup", "hit")}


def test_fire_service_is_never_written(fire_service, dev_ifc, building_id):
    with pytest.raises(ReadOnlyRegistry):
        fire_service.add_address(building_id, "5 rue Autre, Paris", online=False)
    with pytest.raises(ReadOnlyRegistry):
        register(fire_service, dev_ifc, ["5 rue Autre, Paris"], building_id="other-r5", exercise=True, online=False)


def test_copy_local_to_supabase(tmp_path, dev_ifc, building_id):
    src = LocalRegistry(root=tmp_path / "src", online=False)
    register(src, dev_ifc, [ADDRESS], building_id=building_id, exercise=True, online=False)
    dst = SupabaseRegistry(url="https://fake.supabase.co", key="sb_secret_test", online=False,
                           transport=FakeSupabase().transport)
    copy_building(src, dst, building_id)
    assert dst.lookup(ADDRESS).building_id == building_id
    assert dst.read_file(building_id, "building.json") == src.read_file(building_id, "building.json")
