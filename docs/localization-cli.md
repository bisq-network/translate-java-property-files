# Localization CLI

`localize` is the stable command-line entry point for the reusable translation
pipeline. It wraps the same runtime used by Docker and GitHub Actions, so new
projects do not need to import internal Python modules or call Bisq-specific
server scripts.

## Install

From this repository checkout:

```bash
python3 -m venv venv
./venv/bin/pip install -e .
```

For development, install the pinned dev environment instead:

```bash
./venv/bin/pip install pip-tools
./venv/bin/pip-sync requirements-dev.txt
./venv/bin/pip install -e .
```

## Commands

```bash
localize formats
localize init --input-folder path/to/i18n
localize validate --config config.yaml
localize run --config config.yaml
```

- `formats` lists registered format metadata and whether a runtime adapter is
  available.
- `init` delegates to the existing config scaffold helper and detects locales
  from the input folder.
- `validate` checks config shape, paths, locale declarations, format/layout ids,
  and endpoint settings without initializing a model provider.
- `run` executes the configured translation pipeline.

The module form is equivalent and useful before editable install:

```bash
python -m src.cli validate --config config.yaml
python -m src.cli run --config config.yaml
```

## Pipeline Usage

The Docker/server script and GitHub Action call the CLI:

```bash
python -m src.cli run --config "$TRANSLATOR_CONFIG_FILE"
```

That keeps orchestration stable while the internals remain modular:

- `src.core` exposes pipeline and connector contracts.
- `src.formats` exposes format metadata, adapter registration, and conformance
  testing helpers.
- `src.providers` exposes the model-provider abstraction and capabilities.

## Adding A Custom Format

Custom formats register one `LocalizationFileAdapter` at process startup. The
registration also exposes the format id to config loading:

```python
from src.formats import register_localization_adapter

register_localization_adapter(my_adapter)
```

External adapter packages should run the shared conformance helper in their own
tests:

```python
from src.formats.testing import (
    LocalizationAdapterConformanceCase,
    assert_localization_adapter_conformance,
)

assert_localization_adapter_conformance(my_adapter, my_case)
```
