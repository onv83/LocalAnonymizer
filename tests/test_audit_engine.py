"""Synthetic audit regressions for secrets and marker allocation."""
import json

import pytest

from local_anonymizer.engine import Anonymizer, MARKER_RE


@pytest.mark.parametrize("key", ["password", "client_secret", "API_KEY", "DB_PASSWORD"])
def test_quoted_json_secret_keys_use_normal_reversible_markers(key):
    secret = "violetCanary82!"
    result = Anonymizer().anonymize(json.dumps({key: secret}))
    assert secret not in result.text
    assert any(secret in value for value in result.mapping.values())
    assert "[SECRET-" in result.text


def test_json_secret_escaped_quotes_do_not_leave_a_suffix():
    secret = 'violet"canary82!'
    result = Anonymizer().anonymize(json.dumps({"password": secret}))
    assert result.text.startswith('{"password": [SECRET-')
    assert json.dumps(secret) in result.mapping.values()
    assert "canary82" not in result.text


@pytest.mark.parametrize("token", ["violetcanary", "VIOLETCANARY", "abc", "a", "0123", "a-._~+/=="])
def test_explicit_bearer_tokens_use_normal_reversible_markers(token):
    source = "Authorization: " + "Bearer " + token
    result = Anonymizer().anonymize(source)
    assert f"Bearer {token}" not in result.text
    assert token in result.mapping.values()
    assert "[SECRET-" in result.text
    assert all(part.get("orig") for part in result.parts if part.get("secret"))


@pytest.mark.parametrize("compact,label", [(False, "ПОЧТА"), (True, "ПЧ")])
@pytest.mark.parametrize("highest", [999999998, 999999999])
def test_marker_counter_wraps_without_colliding_with_literals(compact, label, highest):
    literals = f"[{label}-1] [{label}-2] [{label}-{highest}] [{label}-1000000000]"
    source = literals + " contact@example.com other@example.com contact@example.com"
    result = Anonymizer(compact_markers=compact).anonymize(source)
    assert result.text.startswith(literals + " ")
    assert len(result.mapping) == 2
    assert all(MARKER_RE.fullmatch(marker) for marker in result.mapping)
    assert all(marker not in literals for marker in result.mapping)
    restored = MARKER_RE.sub(lambda m: result.mapping.get(m.group(), m.group()), result.text)
    assert restored == source
