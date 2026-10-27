from local_anonymizer.app import AppApi


def test_self_test_proves_word_settings_restoration(tmp_path):
    api = AppApi(root=tmp_path / 'library')
    try:
        assert api.engine_self_test().get('word_settings_restore_ok') is True
    finally:
        api.service.storage.connection.close()


def test_self_test_fails_closed_when_word_settings_proof_fails(tmp_path, monkeypatch):
    import local_anonymizer.app as app
    monkeypatch.setattr(app, '_word_settings_restore_self_test', lambda: False, raising=False)
    api = AppApi(root=tmp_path / 'library')
    try:
        report = api.engine_self_test()
        assert report.get('word_settings_restore_ok') is False
        assert report['ok'] is False
    finally:
        api.service.storage.connection.close()
