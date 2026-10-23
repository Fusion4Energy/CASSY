import pytest


@pytest.fixture(autouse=True)
def _geometry_cache(tmp_path_factory, monkeypatch):
    """Keep the simplified meshes of the tests out of the user cache folder."""
    monkeypatch.setenv("CASSY_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
