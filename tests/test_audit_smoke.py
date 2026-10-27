from local_anonymizer.app import AppApi


def test_packaged_self_test_has_required_audit_proof(tmp_path):
    api = AppApi(root=tmp_path / "library")
    try:
        report = api.engine_self_test()
        assert report.get("audit_secret_marker_ok") is True
    finally:
        api.service.storage.connection.close()


def test_packaged_self_test_fails_if_audit_proof_fails(tmp_path, monkeypatch):
    import local_anonymizer.app as app
    monkeypatch.setattr(app, "_audit_secret_marker_self_test", lambda: False, raising=False)
    api = AppApi(root=tmp_path / "library")
    try:
        report = api.engine_self_test()
        assert report["ok"] is False
        assert report.get("audit_secret_marker_ok") is False
    finally:
        api.service.storage.connection.close()
