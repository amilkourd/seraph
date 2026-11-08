from pathlib import Path

import pytest

from seraph_ifc import author, extract

IFC_DIR = Path(__file__).resolve().parents[1]
REPO = IFC_DIR.parent
TUWIEN = IFC_DIR / "test" / "tuwien" / "RealWorldTestModel-EscapeRouteAnalysis-ZDB-v2.ifc"


@pytest.fixture(scope="session")
def dev_ifc(tmp_path_factory) -> Path:
    """The fictional R+5, authored fresh from its trace."""
    return author.build(IFC_DIR / "dev" / "trace.yaml", tmp_path_factory.mktemp("dev") / "dev.ifc")


@pytest.fixture(scope="session")
def dev(dev_ifc) -> extract.Result:
    return extract.extract(dev_ifc)


@pytest.fixture(scope="session")
def tuwien() -> extract.Result:
    if not TUWIEN.exists():
        pytest.skip("TU Wien IFC not downloaded (ifc/test/tuwien/, see ifc/README.md)")
    return extract.extract(TUWIEN, ids=extract.load_ids(IFC_DIR / "tuwien" / "ids.yaml"))
