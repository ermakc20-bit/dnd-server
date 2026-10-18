# DnD VTT Development Contract

Work repository-first for features, fixes, refactors, migrations, release
preparation, and implementation planning. Inspect the relevant source, tests,
current diff, and repository commands; use additional skills only when their
narrow specialty is actually needed.

Repository truth lives in:

1. this file;
2. source, tests, CI, and runbooks;
3. `docs/specs/` and `docs/adr/` when the requested change depends on them.

A legacy command and release-reference catalog remains in the repository for
tooling compatibility. It is not an obligatory workflow, plan, or source of
product truth and should be opened only for an explicit tooling task.

The product is a greenfield, Owlbear Rodeo 2.0-inspired, map-first VTT. Do not
restore the legacy monolith or its competing event/state/save systems. The
legacy snapshot is preserved by the `legacy-4940146` tag.

FastAPI is the sole gameplay authority. Durable state belongs in Supabase
Postgres; Redis is ephemeral. React may use Supabase Auth and approved Storage
flows, but it must not mutate gameplay tables through the Data API.

For complex specifications, validate requirement-to-evidence traceability.
Run focused repository checks first and `make verify` when risk warrants it. Do not push,
merge, deploy, change secrets, or mutate external systems without explicit
authority.

<!-- autopilot:start -->
# DnD VTT

Русскоязычная, map-first VTT-платформа для мастеров и игроков настольных ролевых игр.

## Команды

| Команда | Что делает |
|---------|------------|
| `make bootstrap` | Установить зависимости |
| `make dev-backend` | Запустить API локально |
| `make dev-frontend` | Запустить интерфейс локально |
| `make verify` | Прогнать основные проверки проекта |

## Как здесь работает Autopilot

Сборка ведётся навыком `/autopilot`. Требования, спецификация и таски — в `.autopilot/`.
Прогресс — `.autopilot/dashboard.html`. Правило: требование из `manifest.md`
может снять только пользователь.

Если работа продолжается — скажи «продолжи автопилот»: состояние поднимется
из `.autopilot/state.js`, переспрашивать ничего не нужно.
<!-- autopilot:end -->
