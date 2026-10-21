from wizard.cli.tui import services


def test_local_stack_uses_wizard_configuration_from_other_directory(tmp_path, monkeypatch):
    root = tmp_path / "Wizard"
    root.mkdir()
    (root / ".env").write_text("WIZARD_ACCOUNT_URL=http://localhost:3000\nWIZARD_ACCOUNT_LOCAL_DEV=1\n")
    launcher = root / "backend/scripts/start-local-account-backend.ps1"
    launcher.parent.mkdir(parents=True)
    launcher.touch()
    website = tmp_path / "Wizard-web/wizardsite"
    cli = website / "node_modules/next/dist/bin/next"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.delenv("WIZARD_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("WIZARD_ACCOUNT_LOCAL_DEV", raising=False)
    monkeypatch.delenv("WIZARD_WEBSITE_DIR", raising=False)
    monkeypatch.setattr(services.shutil, "which", lambda name: "node")
    monkeypatch.chdir(tmp_path)
    specs = services.build_account_specs(root)
    assert [s.key for s in specs] == ["account", "website"]
    assert specs[1].cwd == str(website)
    assert specs[1].health_path == "/api/auth/context"
    assert specs[1].env["WIZARD_ACCOUNT_LOCAL_DEV"] == "1"
    assert str(cli) in specs[1].argv
    assert specs[1].argv[specs[1].argv.index("--hostname") + 1] == "127.0.0.1"


def test_remote_account_service_is_never_started(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_ACCOUNT_URL", "https://accounts.example.com")
    monkeypatch.setenv("WIZARD_ACCOUNT_LOCAL_DEV", "1")
    assert services.build_account_specs(tmp_path) == []


def test_supervisor_preserves_owned_children_if_later_start_raises(tmp_path, monkeypatch):
    first = services.ServiceSpec("account", "Account", 8090, "/health", str(tmp_path), None)
    second = services.ServiceSpec("website", "Website", 3000, "/", str(tmp_path), None)
    owned = object()
    def ensure(spec, logs):
        if spec is second:
            raise KeyboardInterrupt
        return services.ServiceState(spec, "started", process=owned)
    monkeypatch.setattr(services, "ensure_service", ensure)
    supervisor = services.ServiceSupervisor(tmp_path)
    import pytest
    with pytest.raises(KeyboardInterrupt):
        supervisor.ensure_all([first, second])
    assert supervisor.report.states[0].process is owned
