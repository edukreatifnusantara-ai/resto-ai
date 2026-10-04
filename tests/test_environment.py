from app.environment import load_environment


def test_project_dotenv_has_priority_over_legacy_runtime_file(tmp_path, monkeypatch):
    import os

    legacy_file = tmp_path / ".env.runtime"
    local_file = tmp_path / ".env"
    legacy_file.write_text(
        "OPENAI_API_KEY=legacy-test-key\nWHATSAPP_ACCESS_TOKEN=legacy-test-token\n",
        encoding="utf-8",
    )
    local_file.write_text("OPENAI_API_KEY=project-test-key\n", encoding="utf-8")

    monkeypatch.setenv("RESTO_ENV_FILE", str(legacy_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)

    load_environment(tmp_path)

    assert os.environ["OPENAI_API_KEY"] == "project-test-key"
    assert os.environ["WHATSAPP_ACCESS_TOKEN"] == "legacy-test-token"


def test_load_environment_preserves_inherited_environment(tmp_path, monkeypatch):
    import os

    legacy_file = tmp_path / ".env.runtime"
    local_file = tmp_path / ".env"
    legacy_file.write_text("OPENAI_API_KEY=legacy-test-key\n", encoding="utf-8")
    local_file.write_text("OPENAI_API_KEY=project-test-key\n", encoding="utf-8")

    monkeypatch.setenv("RESTO_ENV_FILE", str(legacy_file))
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-test-key")

    load_environment(tmp_path)

    assert os.environ["OPENAI_API_KEY"] == "inherited-test-key"
