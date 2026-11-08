# Contributing

1. Read [SYSTEM.md](SYSTEM.md), then [docs/01-architecture.md](docs/01-architecture.md) and every file in
   [contracts/](contracts/).
2. Each top-level folder is one module with its own dependencies and tests. Keep a change inside one module. A
   change to `contracts/` lands first, on its own, with both sides updated.
3. Every service runs in fixture mode (`MOCK=1`) on `contracts/fixtures/`. Every external call has a timeout, a
   cached fallback and a visible state on the command post.
4. The safety rules in [docs/07-safety-rules.md](docs/07-safety-rules.md) are product requirements: the commander
   decides, Gabriel relays; code computes positions and routes, models never guess them.
5. UI text in French (radio French: short, no politeness). Code, comments and docs in English.
6. Secrets only from `.env`. Never hardcode or print a key.
7. Before pushing: `make test` and `make typecheck`. Commit messages read `<module>: <what changed>`.
