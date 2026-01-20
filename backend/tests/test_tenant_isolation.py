"""Tests for tenant isolation helpers."""
import pytest
from uuid import UUID
from fastapi import HTTPException

from app.core.tenant import get_effective_team_id, resolve_ingest_team_id
from app.core.config import get_settings


class DummyApiKey:
    def __init__(self, team_id):
        self.team_id = team_id


def test_get_effective_team_id_requires_key_in_multi_tenant():
    settings = get_settings()
    original_multi = settings.MULTI_TENANT
    original_single = settings.SINGLE_TENANT_TEAM_ID
    settings.MULTI_TENANT = True
    settings.SINGLE_TENANT_TEAM_ID = ""
    try:
        with pytest.raises(HTTPException) as exc:
            get_effective_team_id(None)
        assert exc.value.status_code == 401
    finally:
        settings.MULTI_TENANT = original_multi
        settings.SINGLE_TENANT_TEAM_ID = original_single


def test_get_effective_team_id_returns_api_key_team():
    settings = get_settings()
    original_multi = settings.MULTI_TENANT
    settings.MULTI_TENANT = True
    try:
        team_id = UUID("00000000-0000-0000-0000-000000000001")
        api_key = DummyApiKey(team_id)
        assert get_effective_team_id(api_key) == team_id
    finally:
        settings.MULTI_TENANT = original_multi


def test_single_tenant_rejects_mismatched_api_key():
    settings = get_settings()
    original_multi = settings.MULTI_TENANT
    original_single = settings.SINGLE_TENANT_TEAM_ID
    settings.MULTI_TENANT = False
    settings.SINGLE_TENANT_TEAM_ID = "00000000-0000-0000-0000-000000000001"
    try:
        api_key = DummyApiKey(UUID("00000000-0000-0000-0000-000000000002"))
        with pytest.raises(HTTPException) as exc:
            get_effective_team_id(api_key)
        assert exc.value.status_code == 403
    finally:
        settings.MULTI_TENANT = original_multi
        settings.SINGLE_TENANT_TEAM_ID = original_single


def test_resolve_ingest_team_id_single_tenant_defaults():
    settings = get_settings()
    original_multi = settings.MULTI_TENANT
    original_single = settings.SINGLE_TENANT_TEAM_ID
    settings.MULTI_TENANT = False
    settings.SINGLE_TENANT_TEAM_ID = "00000000-0000-0000-0000-000000000003"
    try:
        resolved = resolve_ingest_team_id(None)
        assert str(resolved) == settings.SINGLE_TENANT_TEAM_ID
    finally:
        settings.MULTI_TENANT = original_multi
        settings.SINGLE_TENANT_TEAM_ID = original_single


def test_resolve_ingest_team_id_requires_team_in_multi_tenant():
    settings = get_settings()
    original_multi = settings.MULTI_TENANT
    settings.MULTI_TENANT = True
    try:
        with pytest.raises(HTTPException) as exc:
            resolve_ingest_team_id(None)
        assert exc.value.status_code == 400
    finally:
        settings.MULTI_TENANT = original_multi
