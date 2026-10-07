# Contributing to RapidKit

Thanks for your interest in improving RapidKit.

## Before you start

Most of this codebase can only be meaningfully tested against real Teslasuit
hardware (v4.x or XR5) with Teslasuit Control Center and Studio running. If
you don't have hardware access, you can still contribute: documentation
fixes, type/lint cleanups, example-code readability, and changes that don't
require a live device are all welcome and reviewable without hardware.

## Development setup

1. Install the Teslasuit Python SDK per the official
   [getting-started guide](https://documentation.teslasuit.io/docs/apis/python/introduction/getting-started).
2. Clone this repository and install it in editable mode:

   ```bash
   git clone https://github.com/teslasuit/RapidKit.git
   cd RapidKit
   pip install -e ".[gui]"
   ```

3. Confirm the install: `python -c "import teslasuit_rapidkit; print(teslasuit_rapidkit.__version__)"`.

## Branching model

- **`main`** — stable, released code. Tags and releases are cut from here.
- **`develop`** — integration branch for the next release; pre-release
  testing happens here before a merge to `main`.
- **`feature/<short-description>`** — all ongoing work. Branch off
  `develop`, not `main`.

## Making a change

- **Bug reports and feature requests:** open an issue describing the problem,
  expected behavior, and (for bugs) steps to reproduce, including whether it
  requires specific hardware.
- **Pull requests:** branch off `develop` as `feature/<short-description>`
  and open the PR against `develop`. Keep changes focused — separate
  unrelated fixes into separate PRs. Describe what you tested it against
  (which hardware, if any) in the PR description.
- **Adding a new example:** follow the structure of an existing one under
  [`examples/`](examples/) — a `main.py` entry point, a `README.md` with
  hardware requirements and run instructions, and application-specific code
  kept inside that example's own folder rather than added to the framework
  package.

## Code style

Match the surrounding code: type hints on public functions, docstrings on
classes and non-obvious methods, no framework-level changes bundled into an
example PR (and vice versa).

## License

By submitting a pull request, you agree that your contribution is licensed
under this repository's [MIT license](LICENSE).
