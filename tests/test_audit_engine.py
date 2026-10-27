"""Synthetic audit regressions for irreversible secrets and marker allocation."""
import json
from dataclasses import asdict

import pytest

from local_anonymizer.engine import Anonymizer, MARKER_RE


@pytest.mark.parametrize("key", ["password", "client_secret", "API_KEY", "DB_PASSWORD"])
def test_quoted_json_secret_keys_are_irreversible(key):
    secret = "violetCanary82!"
    result = Anonymizer().anonymize(json.dumps({key: secret}))
    assert secret not in json.dumps(asdict(result), ensure_ascii=False)
    assert "(удалено)" in result.text
    assert secret not in result.mapping.values()


def test_json_secret_escaped_quotes_do_not_leave_a_suffix():
    secret = 'violet"canary82!'
    result = Anonymizer().anonymize(json.dumps({"password": secret}))
    assert result.text == '{"password": (удалено)}'
    assert result.mapping == {}
    assert "canary82" not in json.dumps(asdict(result))


@pytest.mark.parametrize("token", ["violetcanary", "VIOLETCANARY", "abc", "a", "0123", "a-._~+/=="])
def test_explicit_bearer_tokens_do_not_require_complexity(token):
    result = Anonymizer().anonymize(f"Authorization: Bearer {token}")
    assert result.text == "Authorization: Bearer (удалено)"
    assert result.mapping == {}
    assert result.legend == []
    assert all(not part.get("orig") for part in result.parts if part.get("secret"))


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
