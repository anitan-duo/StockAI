"""Readiness endpoint must not claim vendor connectivity from configuration alone."""

import json
from types import SimpleNamespace

import pytest

from apps.api.routes.health import readiness_check
from services.ingestion.providers.factory import ProviderFactory


class _HealthyDatabaseSession:
    async def execute(self, _statement):
        return object()


@pytest.mark.asyncio
async def test_readiness_reports_provider_configuration_not_connectivity(monkeypatch):
    router = SimpleNamespace(providers={"US": [object()], "India": [object()]})
    monkeypatch.setattr(ProviderFactory, "get_router", lambda: router)

    response = await readiness_check(session=_HealthyDatabaseSession())
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["checks"]["database"]["status"] == "healthy"
    assert body["checks"]["provider"]["status"] == "configured"
    assert body["checks"]["provider"]["connectivity_verified"] is False
    assert body["checks"]["provider"]["providers"] == 2


@pytest.mark.asyncio
async def test_readiness_reports_provider_not_configured(monkeypatch):
    router = SimpleNamespace(providers={})
    monkeypatch.setattr(ProviderFactory, "get_router", lambda: router)

    response = await readiness_check(session=_HealthyDatabaseSession())
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["checks"]["provider"]["status"] == "not_configured"
    assert body["checks"]["provider"]["connectivity_verified"] is False
