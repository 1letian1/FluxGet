import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from backend.api.app import create_app


@asynccontextmanager
async def local_http_server(body: bytes = b"local download payload"):
    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()
            while (header := await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass
            writer.write(b"HTTP/1.1 200 OK\r\n")
            writer.write(f"Content-Length: {len(body)}\r\n".encode())
            writer.write(b"Content-Type: application/octet-stream\r\nConnection: close\r\n\r\n")
            writer.write(body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/artifact.bin"
    finally:
        server.close()
        await server.wait_closed()


@pytest_asyncio.fixture
async def api(tmp_path: Path):
    token = "integration-test-token"
    wrapped = create_app(token, tmp_path / "state" / "test.sqlite3")
    inner_app = wrapped.app
    async with inner_app.router.lifespan_context(inner_app):
        transport = httpx.ASGITransport(app=wrapped)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                    headers={"X-Session-Token": token}) as client:
            yield client


async def wait_for_status(client: httpx.AsyncClient, task_id: str, statuses: set[str]) -> dict:
    for _ in range(150):
        response = await client.get("/api/v1/tasks")
        task = next(item for item in response.json()["items"] if item["id"] == task_id)
        if task["status"] in statuses:
            return task
        await asyncio.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not reach one of {statuses}")


@pytest.mark.asyncio
async def test_session_token_protects_api_but_not_health(tmp_path: Path) -> None:
    wrapped = create_app("secret", tmp_path / "auth.sqlite3")
    inner_app = wrapped.app
    async with inner_app.router.lifespan_context(inner_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url="http://test") as client:
            assert (await client.get("/api/v1/health")).status_code == 200
            assert (await client.get("/api/v1/settings")).status_code == 401
            assert (await client.get("/api/v1/settings", headers={"X-Session-Token": "wrong"})).status_code == 401


@pytest.mark.asyncio
async def test_settings_and_custom_rule_preview_round_trip(api: httpx.AsyncClient, tmp_path: Path) -> None:
    settings = (await api.get("/api/v1/settings")).json()
    settings.update(output_dir=str(tmp_path / "downloads"), concurrency=2, max_retries=1,
                    conflict_policy="skip", current_mode="rule")
    settings.pop("updated_at")
    saved = await api.put("/api/v1/settings", json=settings)
    assert saved.status_code == 200
    assert (await api.get("/api/v1/settings")).json()["concurrency"] == 2
    assert (await api.put("/api/v1/settings", json={**settings, "concurrency": 33})).status_code == 422

    created = await api.post("/api/v1/rules", json={
        "name": "Local test rule", "base_url": "https://example.test/files",
        "url_template": "{base_url}/{name}/{version}/{filename}.{ext}",
        "filename_template": "{filename}.{ext}", "default_ext": "zip",
    })
    assert created.status_code == 201
    rule_id = created.json()["id"]
    preview = await api.post(f"/api/v1/rules/{rule_id}/preview", json={"inputs": "plugin 1.2\ninvalid"})
    assert preview.status_code == 200
    assert [item["valid"] for item in preview.json()["items"]] == [True, False]
    assert preview.json()["items"][0]["url"] == "https://example.test/files/plugin/1.2/plugin.zip"
    assert (await api.delete(f"/api/v1/rules/{rule_id}")).json() == {"deleted": True}


@pytest.mark.asyncio
async def test_direct_task_downloads_atomically_and_records_history(api: httpx.AsyncClient, tmp_path: Path) -> None:
    payload = b"integration payload\x00" * 2048
    async with local_http_server(payload) as url:
        response = await api.post("/api/v1/tasks/direct", json={
            "urls": f"{url}\nnot a URL", "output_dir": str(tmp_path / "downloads"), "subdir": "nested",
        })
        assert response.status_code == 201
        assert len(response.json()["created"]) == 1
        assert len(response.json()["errors"]) == 1
        task_id = response.json()["created"][0]["id"]

        task = await wait_for_status(api, task_id, {"completed", "failed"})
        assert task["status"] == "completed"
        target = tmp_path / "downloads" / "nested" / "artifact.bin"
        assert target.read_bytes() == payload
        assert not target.with_name(target.name + ".part").exists()
        history = await api.get("/api/v1/tasks/history")
        assert [item["id"] for item in history.json()["items"]] == [task_id]


@pytest.mark.asyncio
async def test_existing_destination_can_be_skipped_and_stays_in_history(api: httpx.AsyncClient, tmp_path: Path) -> None:
    out = tmp_path / "downloads"
    out.mkdir()
    (out / "artifact.bin").write_bytes(b"keep existing")
    async with local_http_server() as url:
        created = await api.post("/api/v1/tasks/direct", json={"urls": url, "output_dir": str(out)})
        task_id = created.json()["created"][0]["id"]
        waiting = await wait_for_status(api, task_id, {"waiting_user", "failed"})
        assert waiting["status"] == "waiting_user"

        skipped = await api.post(f"/api/v1/tasks/{task_id}/conflict-resolution", json={"resolution": "skip"})
        assert skipped.status_code == 200
        assert skipped.json()["status"] == "skipped"
        assert (await api.get("/api/v1/tasks/history")).json()["items"][0]["status"] == "skipped"
        assert (out / "artifact.bin").read_bytes() == b"keep existing"
