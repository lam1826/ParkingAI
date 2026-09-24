"""Provider failures must be diagnosable without recording credentials or prompts."""
import logging

import pytest
from google.genai import errors as genai_errors

from services.ai_service import _provider_http_exception


@pytest.mark.parametrize(("failure", "expected_http", "expected_log"), [
    (genai_errors.ClientError(429, {"error": {
        "status": "RESOURCE_EXHAUSTED", "message": "private-key-and-prompt",
    }}), 503, "category=api code=429 status=RESOURCE_EXHAUSTED"),
    (genai_errors.ServerError(503, {"error": {
        "status": "private-key-and-prompt", "message": "private-key-and-prompt",
    }}), 503, "category=api code=503 status=unknown"),
    (ConnectionError("private-key-and-prompt"), 503, "category=network code=none status=unknown"),
    (TimeoutError("private-key-and-prompt"), 504, "category=timeout code=none status=unknown"),
])
def test_wrapped_failure_logs_only_safe_diagnostic_metadata(caplog, failure, expected_http, expected_log):
    outer = RuntimeError("private-key-and-prompt")
    outer.__cause__ = failure
    with caplog.at_level(logging.WARNING, logger="services.ai_service"):
        response = _provider_http_exception(outer)
    assert response.status_code == expected_http
    assert expected_log in caplog.text
    assert "private-key-and-prompt" not in caplog.text
    assert "private-key-and-prompt" not in response.detail
    assert all(record.exc_info is None for record in caplog.records)
