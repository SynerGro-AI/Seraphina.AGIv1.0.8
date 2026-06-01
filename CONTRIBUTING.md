# Contributing

Thanks for considering a contribution to Seraphina.AGI.

## Quick start

```bash
git clone https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git
cd Seraphina.AGIv1.0.8
python -m venv .venv
. .venv/Scripts/activate          # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -e .
seraphina --version
```

No third-party runtime deps. Python 3.9+. The `[grok]` extra is the only
optional install, and it just enables the xAI planner CLI.

## Ground rules

1. **Determinism is the product.** No new code paths that depend on
   wall-clock randomness, network calls, or model temperature in the hot
   path. The Triad must produce the same output for the same input,
   every time.
2. **Stdlib-only by default.** New runtime dependencies need explicit
   discussion in an issue first.
3. **Tests for new behavior.** Add a test under `tests/` for any
   non-trivial change.
4. **Small PRs.** One concern per PR. Easier to review, faster to merge.

## Branch + commit conventions

- Branch off `main` as `feat/<topic>`, `fix/<topic>`, or `docs/<topic>`.
- Commit messages use Conventional Commits prefixes (`feat:`, `fix:`,
  `docs:`, `ci:`, `chore:`, `test:`, `refactor:`).
- Squash-merge to `main`. No direct pushes.

## Running the test suite

```bash
python -m unittest discover tests -v
```

For RWAST changes specifically:

```bash
python -c "from seraphina.rwl.ast_ir import translate; \
  print(translate(open('examples/hello.py').read(), 'python', 'js'))"
```

## Releasing (maintainers only)

1. Bump version in `pyproject.toml` **and** `seraphina/__init__.py`
2. Update README "What's new" section
3. Update `release-notes-v<x.y.z>.md`
4. Commit, tag `vX.Y.Z`, push tag
5. GitHub Actions publishes to PyPI via Trusted Publisher (OIDC)
6. Create the GitHub Release from the notes file

## Code of conduct

Be kind, be specific, be patient. Disagreement is fine; cruelty is not.
By participating, you agree to keep discussions civil and on-topic.

## License

By contributing, you agree your contributions are licensed under the
[MIT License](LICENSE) of this repository.
