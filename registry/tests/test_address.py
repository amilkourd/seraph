import pytest

from building_registry.address import id_kind, normalize


@pytest.mark.parametrize("raw, key", [
    ("2 rue Madame, 64000 Pau", "2 rue madame 64000 pau"),
    ("2, Rue MADAME - 64000 PAU", "2 rue madame 64000 pau"),
    ("35, Bd Haussmann — 75009 Paris, France", "35 boulevard haussmann 75009 paris"),
    ("12 av. du Général-de-Gaulle", "12 avenue du general de gaulle"),
    ("1 rue de l’Exercice", "1 rue de l exercice"),
    ("4bis Pl. St-Michel CEDEX", "4 bis place saint michel"),
])
def test_normalize(raw, key):
    assert normalize(raw) == key


@pytest.mark.parametrize("bid, kind", [("7RE2ZT12JGFM", "rnb"), ("tuwien-escape-route-v2", "manual"),
                                       ("dev-r5-exercice", "manual"), ("Bad Id", None), ("ab", None)])
def test_id_kind(bid, kind):
    assert id_kind(bid) == kind
