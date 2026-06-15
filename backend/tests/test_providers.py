"""Provider unit tests: result factories, each provider, registry, aggregator.
All offline — http_client is monkeypatched per module, exactly like
tests/test_connectors.py."""
from app.providers import base
from app.providers.base import ProviderContext


def test_result_factories_set_status():
    assert base.ok("x", "X", {"v": 1}).status == "ok"
    assert base.empty("x", "X", "none").status == "empty"
    nk = base.needs_key("x", "X", "FOO_KEY")
    assert nk.status == "needs_key" and "FOO_KEY" in nk.message
    assert base.error("x", "X", "boom").status == "error"
    assert base.coming_soon("x", "X", 2).status == "coming_soon"
