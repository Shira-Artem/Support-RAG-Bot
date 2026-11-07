from app.instance_lock import single_instance


def test_instance_lock_uses_isolated_runtime_path(monkeypatch, tmp_path):
    lock_path = tmp_path / 'private-alpha.lock'
    monkeypatch.setenv('BOT_INSTANCE_LOCK_PATH', str(lock_path))
    with single_instance():
        assert lock_path.exists()
