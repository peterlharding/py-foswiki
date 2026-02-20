#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""Tests for /api/v1/auth/* endpoints."""

from __future__ import annotations
import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice Smith",
            "password": "SecurePass1!",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "alice"
        assert body["display_name"] == "Alice Smith"
        assert body["wiki_name"] == "AliceSmith"
        assert "hashed_password" not in body

    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "bob", "email": "bob@example.com", "password": "BobPass123!"}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json={**payload, "email": "bob2@example.com"})
        assert resp.status_code == 409

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = {"username": "carol", "email": "carol@example.com", "password": "Pass1234!"}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json={**payload, "username": "carol2"})
        assert resp.status_code == 409

    async def test_register_invalid_username(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "bad user!",
            "email": "bad@example.com",
            "password": "Pass1234!",
        })
        assert resp.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "dave",
            "email": "dave@example.com",
            "password": "short",
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "eve",
            "email": "eve@example.com",
            "password": "EvePass123!",
        })
        resp = await client.post("/api/v1/auth/login", data={
            "username": "eve",
            "password": "EvePass123!",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "frank",
            "email": "frank@example.com",
            "password": "RealPass123!",
        })
        resp = await client.post("/api/v1/auth/login", data={
            "username": "frank",
            "password": "WrongPass!",
        })
        assert resp.status_code == 401

    async def test_login_unknown_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", data={
            "username": "nobody",
            "password": "whatever",
        })
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestMe:
    async def test_me_returns_user(self, client: AsyncClient):
        headers = await auth_headers(client, "grace")
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "grace"

    async def test_me_without_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_update_display_name(self, client: AsyncClient):
        headers = await auth_headers(client, "henry")
        resp = await client.put("/api/v1/auth/me", json={"display_name": "Henry Updated"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Henry Updated"
        assert resp.json()["wiki_name"] == "HenryUpdated"



