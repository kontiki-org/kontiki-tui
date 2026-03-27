# Contributing to KontikiTUI

This repository follows the same contribution spirit as [Kontiki](https://github.com/kontiki-org/kontiki). For general expectations (maintainer-led model, opening an issue for non-trivial work), see [Contributing to Kontiki](https://github.com/kontiki-org/kontiki/blob/main/CONTRIBUTING.md).

For changes in **this repo**, please:

- Open an issue first for non-trivial work and describe the problem, the intended scope, and how it fits the TUI’s role as a small monitoring tool.
- Prefer **small, focused** pull requests with tests when behavior changes.
- Match existing style (`make fmt`, `make lint`); CI runs tests and flake8 on Python 3.11–3.13.

## Local checks

```bash
make install
make test
make lint
```

By contributing, you agree your contribution is licensed under the same terms as this project ([Apache License 2.0](LICENSE)).
