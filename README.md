# piano-trainer

Личный музыкальный тренажёр: от любимого фрагмента до уверенного исполнения за несколько минут в день.

- [Идея](docs/IDEA.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Как запускать](docs/RUNNING.md)

## Быстрый старт

Нужны Node 24+, pnpm (`npm i -g pnpm`), для OMR — Python 3.12 и [uv](https://docs.astral.sh/uv/), для инфраструктуры — Docker.

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm dev:mobile
```
