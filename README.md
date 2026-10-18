# DnD VTT

Русскоязычный map-first стол: кампании и комнаты, защищённый гостевой вход,
карта/сетка/токены, независимые карточки и ресурсы, проверяемый импорт,
ручной туман/метки/линейка, серверные кубы и журнал, геометрия способностей,
восстановление соединения и полный перенос кампании ZIP.

FastAPI — единственный gameplay authority. Postgres хранит подтверждённое
состояние и события; Redis — ephemeral presence/tickets/previews/fan-out.
React использует Auth и разрешённые private Storage flows, а не пишет gameplay
через Data API. Legacy snapshot сохранён тегом `legacy-4940146`.
Developer OS — спецификации/ADR/evidence/checks; legacy development/design
prototypes не активируются и не маршрутизируют работу.

Для другого ПК с Windows: [пошаговый запуск через WSL2 и Docker Desktop](docs/runbooks/windows-setup.md).
База раунда тестирования от 18 октября 2026 года собрана в [ветке `main`](https://github.com/ermakc20-bit/dnd-server/tree/main):
принятая версия приложения — `aed9735`; ветка `design` с Windows-инструкцией включена целиком.
Инструкция клонирует `main` и отдельно указывает непроверенные Windows-шаги. Для отчётов о тестах сохраняйте полный SHA своего checkout.

## Локальная установка

Нужны Python 3.13–3.14, Node 22+, Docker-compatible runtime. Из чистого checkout:

```sh
make bootstrap
npx supabase start
```

CLI Supabase закреплён в project lockfile. Стек локальный и закрытый, его не
следует выставлять наружу. Рабочие сервисы запускаются явно; повторный запуск
не подразумевает reset пользовательской базы.

Скопируйте `.env.example` в локальный `.env`, заполните **локальные** значения:
`VTT_SUPABASE_URL`, `VTT_SUPABASE_PUBLISHABLE_KEY`,
`VTT_SUPABASE_SERVICE_ROLE_KEY`, `VTT_DATABASE_URL`, `VTT_REDIS_URL`.
Vite читает этот же корневой `.env` через `envDir`; отдельная копия в `frontend`
не нужна. Frontend получает только переменные с префиксом `VITE_`:
`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`
и `VITE_API_BASE_URL`; server/service-role keys в него не попадают.
Установку и генерацию ключей нельзя считать hosted приёмкой.

```sh
make dev-backend
make dev-frontend
```

API слушает `127.0.0.1:8000`; интерфейс открывайте на `http://127.0.0.1:5173`.
Этот Origin и `http://localhost:5173` явно разрешены в локальном `.env.example`;
посторонние Origin сервер по-прежнему отклоняет.
Войдите мастером, создайте кампанию/сцену, загрузите карту, скачайте шаблон
карточек и подтвердите импорт после проверки черновиков. Приглашение выдаёт
участнику серверно ограниченный доступ. Его создание не означает отправки.

## Проверки без скрытых пропусков

Интеграционные fixtures требуют отдельную disposable БД `vtt_ticket01` и Redis.
На **новом локальном** SQL-сервисе с Supabase-compatible auth/storage/roles
и установленным pgTAP создайте базу только если она ещё отсутствует:

```sh
export VTT_TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:54322/vtt_ticket01'
export VTT_TEST_REDIS_URL='redis://127.0.0.1:6379/15'
.venv/bin/python scripts/acceptance_database.py --prepare-integration
make verify
make security
make test-database-replay
```

Показанный пароль — стандартный локальный disposable service, не hosted secret.
`--prepare-integration` откажется менять существующую базу. При существующей
подготовленной test БД этот шаг пропускают, а не обходят защиту. Обычный replay
создаёт случайную новую базу, проверяет все migrations/pgTAP и удаляет только её.
`make test-database` — прежний destructive reset локального Supabase; используйте
его только для disposable стека. Безопасная проверка выше не требует reset.

`make verify` сохраняет lint/types/coverage/tests/build и проверяет **все** VTT
specs. Test URLs обязательны; acceptance не допускает skipped integration tests.
`make security` различает scanner error и finding, проверяет bounded code/build
patterns и AI dependency/network references, затем выполняет pip-audit/npm audit.
Совпадения/секреты и содержимое пользовательских документов не выводятся.

## Явная native browser/load приёмка

Используйте уже установленный Playwright module и Chromium/Chrome executable:
никакой автоматической установки браузера или обращения к hosted проекту.

```sh
export VTT_PLAYWRIGHT_MODULE='/absolute/path/to/existing/playwright'
export VTT_CHROME_EXECUTABLE='/absolute/path/to/existing/Chrome'
export VTT_E2E_OUTPUT='/absolute/path/to/temporary/acceptance-output'
make test-e2e
make test-load
```

Output должен быть новым/пустым temporary каталогом либо ранее созданным этим
runner каталогом с ownership marker. Чужие файлы runner не перезаписывает.

Runner создаёт одну synthetic identity, запускает принадлежащие ему API/Vite
на loopback `18010/5190` (можно задать `VTT_E2E_API_PORT/VTT_E2E_WEB_PORT`),
использует новую headless browser session, останавливает только свои процессы и
читает `cleanup.json` с нулевыми account/campaign/job counts. Личный browser
profile не используется. Source env-файлы runner не читает: API стартует с cwd
в новом временном каталоге и явными fixture settings. Frontend entry — actual
AppView, выбранный только explicit test Vite config; production main не меняется.
Synthetic RS256/JWKS verification реальна, private MemoryStorage не доказывает
работу hosted Storage/Auth/sign-in.

Browser проверяет native GM+guest, подтверждённые map/token/template/card,
назначенный token control, ресурс, touch geometry, offline/resync и ZIP roundtrip
с новыми ID и сохранением raster bytes/current resources/geometry. T09 отдельно
проверял mouse/touch drag; T10 не выдаёт предыдущую проверку за новый результат.
Load smoke держит 1+5 и 10 WS connections, проверяет 30 mutations/duplicate receipts,
cursor/version convergence, reconnect и hidden canary. Метрики содержат только
счётчики/время/версии; ZIP и тестовые изображения остаются temporary fixtures.

На macOS с iCloud dataless caches используйте отдельный env-free source snapshot
и новые isolated dependencies; не заменяйте/удаляйте пользовательские окружения.
T10 проверяет свежие Python/Node installations с временными constraints,
сохраняющими остальные принятые версии. В репозитории полного Python lockfile
пока нет; четыре security pins не делают весь graph полностью воспроизводимым.

## Статус доказательств

Точная локальная evidence map: `docs/specs/VTT-010-native-acceptance.md`.
Рынок/референсы в authoritative Autopilot spec — dated 2026-09-03 research:
это основание для пилота, а не доказательство российского TAM/платного спроса.
Пять полных внутренних игр, реальный двадцатиминутный preparation gate,
hosted Auth/Storage/migrations, WAN доступность из России, физические устройства,
Safari/Firefox, actual remote CI и согласие внешней когорты не проверены.
Organic growth, production region и коммерческий этап остаются закрытыми шлюзами.

Source/tests/CI/runbooks, `AGENTS.md`, versioned `docs/specs` и `docs/adr`
определяют реализованный контракт. Локальный technical PASS не снимает real-use
или infrastructure gates и не разрешает push/deploy.
