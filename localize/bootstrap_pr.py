"""Create a self-service onboarding branch for a target repository."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from localize.init_config import (
    build_config,
    detect_locales,
    detect_project_layout,
    render_config,
)


@dataclass(frozen=True)
class BootstrapPrOptions:
    """Options for generating a Localize Pipeline onboarding branch."""

    target_project_root: Path | str = Path(".")
    input_folder: Optional[str] = None
    localization_format: str = "java_properties"
    localization_layout: str = "suffix"
    source_locale: str = "en"
    config_path: str = "config.yaml"
    glossary_path: str = "glossary.json"
    workflow_path: str = ".github/workflows/translate.yml"
    branch_name: str = "localize/onboarding"
    base_branch: Optional[str] = None
    action_ref: str = "v0.1.0"
    commit_message: str = "Add Localize Pipeline onboarding"
    pr_title: str = "Add Localize Pipeline onboarding"
    overwrite: bool = False
    push: bool = False
    open_pr: bool = False


@dataclass(frozen=True)
class BootstrapPrResult:
    """Summary of generated onboarding work."""

    branch_name: str
    created_files: tuple[str, ...]
    commit_sha: str
    pushed: bool = False
    opened_pr: bool = False


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=True,
    )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(("git", *args), cwd=repo, check=check)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _assert_git_repo(repo: Path) -> None:
    result = _git(repo, "rev-parse", "--show-toplevel")
    if Path(result.stdout.strip()).resolve() != repo.resolve():
        raise RuntimeError(f"target_project_root must be the git repository root: {repo}")


def _assert_clean_worktree(repo: Path) -> None:
    status = _git(repo, "status", "--porcelain").stdout.strip()
    if status:
        raise RuntimeError("target repository working tree is not clean.")


def _assert_can_write(repo: Path, relative_paths: Iterable[str], *, overwrite: bool) -> None:
    for relative_path in relative_paths:
        path = repo / relative_path
        if path.exists() and not overwrite:
            raise FileExistsError(f"{relative_path} already exists. Re-run with --overwrite to replace it.")


def _copy_example_glossary(target: Path) -> None:
    source = _project_root() / "glossary.example.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _render_workflow(*, action_ref: str, config_path: str) -> str:
    return f"""name: Translate
on:
  push:
    branches: [main]
  workflow_dispatch: {{}}

permissions:
  contents: write
  pull-requests: write

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: bisq-network/translate-java-property-files@{action_ref}
        with:
          config-file: {config_path}
          openai-api-key: ${{{{ secrets.OPENAI_API_KEY }}}}
          dry-run: true
"""


def _build_onboarding_config(options: BootstrapPrOptions, repo: Path) -> str:
    if options.input_folder:
        input_folder = options.input_folder
        input_folder_abs = repo / input_folder if not Path(input_folder).is_absolute() else Path(input_folder)
        locales = detect_locales(
            str(input_folder_abs),
            source_locale=options.source_locale,
            localization_format=options.localization_format,
            localization_layout=options.localization_layout,
        )
        config = build_config(
            target_project_root=".",
            input_folder=input_folder,
            locales=locales,
            localization_format=options.localization_format,
            localization_layout=options.localization_layout,
            source_locale=options.source_locale,
            dry_run=True,
        )
        return render_config(config)

    detected = detect_project_layout(str(repo), source_locale=options.source_locale)
    if detected is None:
        raise RuntimeError(
            "Could not detect localization files. Pass --input-folder and, if needed, "
            "--localization-format/--localization-layout."
        )

    config = build_config(
        target_project_root=".",
        input_folder=detected.input_folder,
        locales=detected.locales,
        localization_profiles=[
            (profile_format, profile_layout)
            for profile_format, profile_layout in detected.localization_profiles
        ],
        source_locale=options.source_locale,
        dry_run=True,
    )
    if len(detected.localization_profiles) == 1:
        profile_format, profile_layout = detected.localization_profiles[0]
        config = build_config(
            target_project_root=".",
            input_folder=detected.input_folder,
            locales=detected.locales,
            localization_format=profile_format,
            localization_layout=profile_layout,
            source_locale=options.source_locale,
            dry_run=True,
        )
    return render_config(config)


def create_bootstrap_pr(options: BootstrapPrOptions) -> BootstrapPrResult:
    """Create a local onboarding branch and optionally push/open a PR."""
    repo = Path(options.target_project_root).expanduser().resolve()
    _assert_git_repo(repo)
    _assert_clean_worktree(repo)
    created_files = (options.config_path, options.glossary_path, options.workflow_path)
    _assert_can_write(repo, created_files, overwrite=options.overwrite)

    if options.base_branch:
        _git(repo, "checkout", options.base_branch)
    _git(repo, "checkout", "-B", options.branch_name)

    (repo / options.config_path).parent.mkdir(parents=True, exist_ok=True)
    (repo / options.config_path).write_text(_build_onboarding_config(options, repo), encoding="utf-8")
    _copy_example_glossary(repo / options.glossary_path)
    workflow_file = repo / options.workflow_path
    workflow_file.parent.mkdir(parents=True, exist_ok=True)
    workflow_file.write_text(
        _render_workflow(action_ref=options.action_ref, config_path=options.config_path),
        encoding="utf-8",
    )

    _git(repo, "add", *created_files)
    _git(repo, "commit", "-m", options.commit_message)
    commit_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    pushed = False
    opened_pr = False
    if options.push or options.open_pr:
        _git(repo, "push", "-u", "origin", options.branch_name)
        pushed = True
    if options.open_pr:
        _run(
            (
                "gh",
                "pr",
                "create",
                "--title",
                options.pr_title,
                "--body",
                "Adds Localize Pipeline config, glossary, and workflow in dry-run mode.",
            ),
            cwd=repo,
        )
        opened_pr = True

    return BootstrapPrResult(
        branch_name=options.branch_name,
        created_files=created_files,
        commit_sha=commit_sha,
        pushed=pushed,
        opened_pr=opened_pr,
    )
