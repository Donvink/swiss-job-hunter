# Contributing to Swiss Job Hunter

Thanks for your interest in contributing!

## Ways to contribute

- **Bug reports** — open an issue with steps to reproduce and your OS/Python version
- **New job board scrapers** — see [Adding a New Job Board](README.md#adding-a-new-job-board) in the README
- **Feature requests** — open an issue describing the use case before implementing
- **Pull requests** — small, focused PRs are easier to review than large ones

## Development setup

```bash
git clone https://github.com/Donvink/swiss-job-hunter.git
cd swiss-job-hunter

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium

cd ui && npm install && cd ..

cp .env.example .env   # then add your API keys
```

Run tests:

```bash
pytest tests/
```

## Pull request checklist

- [ ] Existing tests pass (`pytest tests/`)
- [ ] New scraper includes at least one unit test with a mocked response
- [ ] No personal data, API keys, or files from `data/` committed
- [ ] CI passes

## License

By submitting a pull request you agree that your contribution will be licensed under [AGPL-3.0](LICENSE).
