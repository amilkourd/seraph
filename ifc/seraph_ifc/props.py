"""Reading IFC properties. A placeholder is not a value: « ND » (nicht definiert), « - », « n/a »… are absent."""
from __future__ import annotations

from typing import Any

import ifcopenshell.util.element as E

NOT_A_VALUE = {"", "nd", "n.d.", "n/a", "na", "-", "--", "none", "keine", "aucun", "aucune", "unknown", "inconnu"}


def pset_value(el, pset: str, prop: str) -> Any:
    v = (E.get_psets(el).get(pset) or {}).get(prop)
    if v is None or (isinstance(v, str) and v.strip().lower() in NOT_A_VALUE):
        return None
    return v
