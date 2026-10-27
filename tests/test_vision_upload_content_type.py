"""An upload with no Content-Type header is a client error, never a 500.

Starlette's MultiPartParser indexes headers["Content-Type"], so a request that
omits the header raised KeyError (not MultiPartException) and surfaced as an
unhandled 500 on all three camera upload endpoints.
"""
import asyncio

import httpx
import pytest

from test_fix20261005_cxvision_round2_upload import setup_app
from test_vision_passage import passage  # noqa: F401

PATHS = ["/api/v2/vision/live-frames", "/api/v2/vision/observations", "/api/v2/vision/edge-events"]


def post(app, path, headers, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path, headers=headers, **kwargs)

    return asyncio.run(run())


@pytest.mark.parametrize("body", [b"", b"x"])
@pytest.mark.parametrize("path", PATHS)
def test_upload_without_content_type_is_rejected_as_client_error(passage, path, body):
    app, _camera_id, staff, edge = setup_app(passage)
    headers = edge if path.endswith("edge-events") else staff
    response = post(app, path, headers, content=body)
    assert "content-type" not in response.request.headers
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("path", PATHS)
def test_upload_with_non_multipart_content_type_is_still_rejected(passage, path):
    app, _camera_id, staff, edge = setup_app(passage)
    headers = {**(edge if path.endswith("edge-events") else staff), "Content-Type": "text/plain"}
    response = post(app, path, headers, content=b"x")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("path", PATHS)
def test_unauthenticated_upload_without_content_type_stays_unauthorized(passage, path):
    app, _camera_id, _staff, _edge = setup_app(passage)
    bogus = {"X-Camera-Token": "Z" * 43} if path.endswith("edge-events") else {"Authorization": "Bearer bogus.bearer.token"}
    response = post(app, path, bogus, content=b"x")
    assert response.status_code == 401, response.text
