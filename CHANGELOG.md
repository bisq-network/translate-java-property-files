# Changelog

All notable changes to Localize Pipeline are documented here.

This project follows semantic versioning once tagged releases begin. Until a
stable `1.0.0`, minor releases may still refine public APIs with migration notes.

## [0.1.0] - 2026-06-28

### Added

- `localize` CLI with `init`, `check`, `validate`, `run`, `formats`, and
  `bootstrap-pr` commands.
- Self-service onboarding branch generation for downstream repositories.
- Built-in Java `.properties` and JSON localization adapters.
- Mixed-format profile support through `localization_formats`.
- AISuite-backed model-provider abstraction with OpenAI-compatible fallback.
- Exact-match translation memory with conflict-safe reuse.
- GitHub Action and Docker Compose cron deployment paths.
- Public `localize.core`, `localize.formats`, and `localize.providers` packages.
