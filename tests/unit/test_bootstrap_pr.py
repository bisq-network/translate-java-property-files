import subprocess
from pathlib import Path

import pytest
import yaml

from localize.bootstrap_pr import BootstrapPrOptions, create_bootstrap_pr


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    resources = repo / "i18n"
    resources.mkdir()
    (resources / "messages.properties").write_text("hello=Hello\n", encoding="utf-8")
    (resources / "messages_de.properties").write_text("hello=Hallo\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Add localization files")


def test_bootstrap_pr_creates_onboarding_branch_commit_and_files(tmp_path):
    repo = tmp_path / "target"
    _init_repo(repo)

    result = create_bootstrap_pr(
        BootstrapPrOptions(
            target_project_root=repo,
            branch_name="localize/onboarding",
            action_ref="v0.1.0",
            push=False,
            open_pr=False,
        )
    )

    assert result.branch_name == "localize/onboarding"
    assert _git(repo, "branch", "--show-current") == "localize/onboarding"
    assert _git(repo, "log", "-1", "--format=%s") == "Add Localize Pipeline onboarding"
    assert result.created_files == (
        "config.yaml",
        "glossary.json",
        ".github/workflows/translate.yml",
    )

    config = yaml.safe_load((repo / "config.yaml").read_text(encoding="utf-8"))
    assert config["target_project_root"] == "."
    assert config["input_folder"] == "i18n"
    assert config["localization_format"] == "java_properties"
    assert config["dry_run"] is True
    assert config["supported_locales"] == [{"code": "de", "name": "German"}]

    workflow = (repo / ".github/workflows/translate.yml").read_text(encoding="utf-8")
    assert "bisq-network/translate-java-property-files@v0.1.0" in workflow
    assert "dry-run: true" in workflow

    glossary = yaml.safe_load((repo / "glossary.json").read_text(encoding="utf-8"))
    assert isinstance(glossary, dict)


def test_bootstrap_pr_refuses_dirty_repo(tmp_path):
    repo = tmp_path / "target"
    _init_repo(repo)
    (repo / "README.md").write_text("uncommitted\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="working tree is not clean"):
        create_bootstrap_pr(BootstrapPrOptions(target_project_root=repo))


def test_bootstrap_pr_refuses_to_overwrite_existing_files_without_flag(tmp_path):
    repo = tmp_path / "target"
    _init_repo(repo)
    (repo / "config.yaml").write_text("dry_run: true\n", encoding="utf-8")
    _git(repo, "add", "config.yaml")
    _git(repo, "commit", "-m", "Add config")

    with pytest.raises(FileExistsError, match="config.yaml"):
        create_bootstrap_pr(BootstrapPrOptions(target_project_root=repo))


def test_bootstrap_pr_uses_custom_config_path_in_workflow(tmp_path):
    repo = tmp_path / "target"
    _init_repo(repo)

    create_bootstrap_pr(
        BootstrapPrOptions(
            target_project_root=repo,
            config_path=".localize/config.yaml",
            branch_name="localize/custom-config",
        )
    )

    workflow = (repo / ".github/workflows/translate.yml").read_text(encoding="utf-8")
    assert "config-file: .localize/config.yaml" in workflow
