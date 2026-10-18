# DnD VTT: запуск на Windows через WSL2

Инструкция для тестовой базы от 18 октября 2026 года в [ветке `main`](https://github.com/ermakc20-bit/dnd-server/tree/main). Принятая кодовая версия приложения — [`aed9735d2b44a74e17880025e74c381ee8f61fbd`](https://github.com/ermakc20-bit/dnd-server/commit/aed9735d2b44a74e17880025e74c381ee8f61fbd); в `main` целиком включена ветка `design` на `13e4d23878b06f0c4b8ec6af6083812a981bd227`, включая Windows-инструкцию. Последующая правка ссылок на `main` и исправления проверок для текущего дизайна приложение не изменяют. Свежие результаты на Mac и границы проверки приведены в [отчёте от 18 октября](main-stability-2026-10-18.md).

Рекомендуемый первый запуск: **Windows 11 → WSL2 / Ubuntu 24.04 → Docker Desktop для Supabase и Redis; Python API и Vite — в Ubuntu**. Это соответствует Linux-командам `Makefile` и путям `.venv/bin/…`. Нативный PowerShell не исполняет этот Makefile без адаптации. Браузер можно использовать обычный, установленный в Windows.

Это локальный стенд на одном ПК. Настройка публичного HTTPS-сервера, доступа из интернета и переноса существующей базы в эту инструкцию не входит. Новый запуск создаёт отдельный локальный набор данных; данные с Mac автоматически не переносятся.

## Что проверено и что ещё нужно проверить

- Сверены исходники этой версии: `README.md`, `Makefile`, оба npm lock-файла, `pyproject.toml`, `compose.yaml`, Dockerfile, конфигурация Supabase, JWT-проверка, миграции и маршруты API.
- На Mac в новом checkout вне iCloud восстановлены зависимости и проверены backend, frontend, сборка и браузерные сценарии с изолированными PostgreSQL 17 и Redis 7.4; подробности — в [отчёте проверки main](main-stability-2026-10-18.md).
- **Windows, WSL2, установка на чистом ПК, настоящий локальный Supabase Auth/Storage и полный сценарий ниже ещё не запускались.** Команды установки сверены с официальной документацией; это инструкция для воспроизведения, а не отчёт об успешном Windows-развёртывании.
- Исходный checkout на Mac имел зависимости iCloud в состоянии `dataless`. Для свежей успешной проверки использован отдельный checkout вне iCloud. На Windows также держите проект в Linux-файловой системе WSL, а не в OneDrive или синхронизируемой папке.

## 1. Установить WSL2 и Docker Desktop

В **PowerShell от администратора**:

```powershell
wsl --install -d Ubuntu-24.04
```

Если система попросит, перезагрузите Windows. Откройте Ubuntu, создайте Linux-пользователя. Затем в PowerShell проверьте:

```powershell
wsl --update
wsl --list --verbose
```

У Ubuntu в колонке `VERSION` должно быть `2`. Если стоит `1`:

```powershell
wsl --set-version Ubuntu-24.04 2
```

Основание: [установка WSL у Microsoft](https://learn.microsoft.com/en-us/windows/wsl/install).

Установите [Docker Desktop для Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Используйте Linux containers, включите **Use the WSL 2 based engine** и интеграцию с Ubuntu-24.04 в **Settings → Resources → WSL Integration**. Виртуализация должна быть включена в BIOS/UEFI.

Дальнейшие команды `bash` выполняйте **в терминале Ubuntu**, не в PowerShell:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates make build-essential
docker version
docker compose version
```

`docker version` должен показать и Client, и Server. Если Server недоступен, сначала запустите Docker Desktop и проверьте WSL Integration. Второй Docker Engine внутри Ubuntu для этого пути не нужен.

## 2. Установить Python и Node внутри Ubuntu

| Компонент | Требование этой кодовой базы |
| --- | --- |
| Python | `>=3.13,<3.15`; здесь используем 3.13 |
| Node.js | ветка 22, версия не ниже 22.12; контейнер frontend также использует Node 22 |
| npm | версия, поставляемая с выбранным Node; установка строго через `npm ci` |
| Supabase CLI | `2.111.0`, закреплён в корневых `package.json` / `package-lock.json` |
| PostgreSQL | Supabase Postgres 17 из `supabase/config.toml` |
| Redis | `redis:7.4-alpine`, как в `compose.yaml` |

Для Python удобно использовать `uv`. Установщик скачивается с сайта его разработчика; выполняйте его только после проверки источника:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/dnd-uv-install.sh
sh /tmp/dnd-uv-install.sh
source "$HOME/.local/bin/env"
uv python install 3.13
uv python find 3.13
```

Документация: [установка uv](https://docs.astral.sh/uv/getting-started/installation/), [управляемые версии Python](https://docs.astral.sh/uv/guides/install-python/).

Для Node установите `nvm` **внутри Ubuntu** по [инструкции Microsoft для Node в WSL2](https://learn.microsoft.com/en-us/windows/dev-environment/javascript/nodejs-on-wsl), затем:

```bash
nvm install 22
nvm use 22
node --version
npm --version
command -v node
```

Путь к Node должен быть Linux-путём, обычно внутри `~/.nvm/`, а не `/mnt/c/Program Files/…`. Python и Node, установленные только в Windows, не заменяют Linux-окружение.

## 3. Клонировать `main` и установить зависимости

```bash
mkdir -p "$HOME/src"
cd "$HOME/src"
git -c core.autocrlf=false clone --branch main --single-branch https://github.com/ermakc20-bit/dnd-server.git
cd dnd-server
git rev-parse HEAD
```

Для текущего раунда тестирования оставайтесь на `main`. Сохраните полный SHA из вывода `git rev-parse HEAD` вместе с отчётом об ошибке: он фиксирует проверенный срез, даже если позднее ветка продолжит развиваться. Код приложения в этой тестовой базе совпадает с `aed9735`; более поздние коммиты добавляют документацию и исправляют проверки для принятого дизайна. Переключаться на старую ветку `master` или на detached-срез без инструкции для обычного запуска не требуется.

Установка из корня проекта:

```bash
make bootstrap PYTHON="$(uv python find 3.13)"
.venv/bin/python --version
npx supabase --version
```

`make bootstrap` создаёт `.venv`, устанавливает `pip==26.2`, Python-пакет с `[dev]`, корневые npm-зависимости и frontend через два `npm ci`. Полного Python lock-файла в этой версии нет: диапазоны из `pyproject.toml` не дают побайтно закреплённого графа Python-зависимостей. Не копируйте `.venv` или `node_modules` с Mac.

Если закреплённая версия пакета недоступна в вашем npm/PyPI-зеркале, сохраните ошибку и проверьте доступ к официальному registry; не заменяйте версии и lock-файлы наугад.

## 4. Настроить подпись локального Supabase Auth

Приложение проверяет JWT через JWKS и принимает **только ES256/RS256** (`backend/app/auth/jwt.py`). HS256 для пользовательского входа не поддерживается. Поэтому на новом стенде задайте асимметричный ключ **до первого `supabase start`**.

В `supabase/config.toml`, в существующем разделе `[auth]`, замените строку:

```toml
# signing_keys_path = "./signing_keys.json"
```

на:

```toml
signing_keys_path = "./.env.signing-keys.json"
```

Не добавляйте второй раздел `[auth]`. Существующие `site_url = "http://127.0.0.1:5173"` и `additional_redirect_urls` для localhost уже соответствуют этому способу запуска.

Проверьте команду установленной, закреплённой версии CLI и создайте локальный файл ключей:

```bash
npx supabase gen signing-key --help
git check-ignore supabase/.env.signing-keys.json
```

Вторая команда должна вывести этот путь: шаблон `.env.*` уже находится в `.gitignore`. Если путь не игнорируется, остановитесь до генерации. Далее:

```bash
if [ ! -e supabase/.env.signing-keys.json ]; then
  (umask 077; printf '[]\n' > supabase/.env.signing-keys.json)
  npx supabase gen signing-key --algorithm ES256 --append
fi
.venv/bin/python - <<'PY'
import json
from pathlib import Path
keys = json.loads(Path("supabase/.env.signing-keys.json").read_text())
assert keys and keys[0].get("alg") in {"ES256", "RS256"}
assert keys[0].get("kid") and keys[0].get("d")
print("Локальный ключ подписи: OK")
PY
```

Этот блок сохраняет существующий файл и не выводит приватный ключ. Если генератор завершился с ошибкой и остался массив `[]`, исправьте причину и повторите только `npx supabase gen signing-key --algorithm ES256 --append`, затем проверку. Не подменяйте реальный ключ примером из документации.

Настройка пути — локальная конфигурация этой машины. Приватный `.env.signing-keys.json` и `.env` не должны попадать в коммиты, переписку или снимки экрана. Не генерируйте новые ключи при каждом запуске: это меняет подпись пользовательских сессий.

Семантика команды и относительного пути сверена по [официальной CLI-справке](https://supabase.com/docs/reference/cli/supabase-gen-signing-key) и [исходнику загрузчика ключей](https://github.com/supabase/cli/blob/develop/apps/cli/src/commands/gen/gen.signing-keys-config.ts). Локальное исполнение CLI на исходном Mac зависало на iCloud-файлах; на Windows этот шаг нужно подтвердить выводом `--help` и проверкой выше. О принципе подписи: [JWT Signing Keys](https://supabase.com/docs/guides/auth/signing-keys).

## 5. Запустить Supabase, применить миграции и запустить Redis

Из корня проекта:

```bash
npx supabase start
npx supabase migration up --help
npx supabase migration up --local
npx supabase migration list --local
```

Первый запуск скачивает контейнеры. Локальная конфигурация уже есть: `supabase init` не требуется. В свежем стеке `start` подготавливает БД с миграциями; `migration up --local` применяет оставшиеся, не выполняя reset. Проверьте, что все 11 файлов из `supabase/migrations` отражены в локальной истории. Миграции создают схему `app`, необходимые таблицы/триггеры и **приватный** bucket `vtt-assets` с лимитом 50 МиБ. Отдельно создавать публичный bucket не нужно.

Обычного `postgres`-контейнера недостаточно: миграции используют Supabase `auth` и `storage`. Не запускайте `supabase db reset` и `make test-database` для исправления ошибок на базе, в которой уже есть нужные данные.

Запустите отдельный локальный Redis с тем же образом и параметрами памяти, что в Compose:

```bash
docker run --name dnd-vtt-redis-local --detach \
  --publish 127.0.0.1:6379:6379 \
  redis:7.4-alpine \
  redis-server --appendonly no --save "" \
  --maxmemory 256mb --maxmemory-policy allkeys-lru
docker exec dnd-vtt-redis-local redis-cli ping
```

Ожидается `PONG`. Если контейнер с этим именем уже создан, вместо повторного `docker run` используйте `docker start dnd-vtt-redis-local`. Долговременное состояние игры хранится в Postgres; этот Redis не сохраняет данные на диск.

## 6. Заполнить корневой `.env`

```bash
cp -n .env.example .env
npx supabase status
nano .env
```

`status` показывает локальные ключи: не отправляйте его полный вывод другим людям. Возьмите URL и ключи **с этого нового локального стенда**, а не с Mac и не из рабочего облачного проекта.

| Переменная | Что указать |
| --- | --- |
| `VTT_SUPABASE_URL` | локальный API URL из `status`, обычно `http://127.0.0.1:54321` |
| `VTT_SUPABASE_PUBLISHABLE_KEY` | локальный Publishable key; если CLI показывает только `anon key`, используйте его как совместимый публичный клиентский ключ |
| `VTT_SUPABASE_SERVICE_ROLE_KEY` | локальный **service_role key**, только для backend; это не приватный ES256 JWK-файл |
| `VTT_DATABASE_URL` | локальный DB URL из `status`; backend принимает `postgresql://…` и `postgresql+asyncpg://…` |
| `VTT_REDIS_URL` | `redis://127.0.0.1:6379/0` |
| `VITE_SUPABASE_URL` | тот же API URL, что в `VTT_SUPABASE_URL` |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | тот же публичный клиентский ключ |

Схема файла после заполнения должна выглядеть так; `PASTE_LOCAL_…` необходимо заменить, это не готовые ключи:

```dotenv
VTT_ENVIRONMENT=local
VTT_FRONTEND_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
VTT_SUPABASE_URL=http://127.0.0.1:54321
VTT_SUPABASE_PUBLISHABLE_KEY=PASTE_LOCAL_PUBLISHABLE_OR_ANON_KEY
VTT_SUPABASE_SERVICE_ROLE_KEY=PASTE_LOCAL_SERVICE_ROLE_KEY
VTT_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
VTT_TEST_DATABASE_URL=
VTT_REDIS_URL=redis://127.0.0.1:6379/0
VITE_SUPABASE_URL=http://127.0.0.1:54321
VITE_SUPABASE_PUBLISHABLE_KEY=PASTE_LOCAL_PUBLISHABLE_OR_ANON_KEY
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`postgres:postgres` здесь — стандартные учётные данные **локального одноразового** Supabase, не пароль удалённого проекта. Если `status` показывает другой DB URL, используйте его. Не помещайте `service_role`, secret API key или приватный JWT-ключ в переменные `VITE_*`: Vite включает их в браузерную сборку. Vite читает `.env` из корня через `envDir: ".."`; отдельный `frontend/.env` не нужен. После изменения `.env` перезапустите оба процесса приложения.

## 7. Запустить API и интерфейс

Откройте два терминала **Ubuntu**, оба — в `~/src/dnd-server`.

Терминал 1:

```bash
make dev-backend
```

Терминал 2:

```bash
make dev-frontend
```

Эти цели запускают соответственно Uvicorn на `127.0.0.1:8000` и Vite на `127.0.0.1:5173`. Vite проксирует `/api` и WebSocket к API. На старте Vite должен сообщить именно порт **5173**; если он выбрал 5174, сначала освободите занятый 5173 или согласованно измените origins/redirects — иначе вход может не работать.

В браузере **Windows** откройте:

| Адрес | Назначение |
| --- | --- |
| `http://127.0.0.1:5173` | приложение DnD VTT |
| `http://127.0.0.1:8000/health/live` | процесс API отвечает |
| `http://127.0.0.1:8000/health/ready` | проверка настроек, **не** соединения с БД/Redis |
| `http://127.0.0.1:8000/docs` | OpenAPI в локальном режиме |
| `http://127.0.0.1:54323` | локальная Supabase Studio |
| `http://127.0.0.1:54324` | локальный почтовый ящик для ссылок входа |

Доступ Windows к Linux-сервисам через localhost описан в [документации WSL](https://learn.microsoft.com/en-us/windows/wsl/networking). Если фактические адреса Supabase отличаются, ориентируйтесь на `npx supabase status`.

Проверка публичных ключей подписи без показа секретов:

```bash
curl -fsS http://127.0.0.1:54321/auth/v1/.well-known/jwks.json \
  | .venv/bin/python -c 'import json,sys; keys=json.load(sys.stdin).get("keys",[]); assert any(k.get("alg") in {"ES256","RS256"} for k in keys); print("JWKS: OK")'
curl -fsS http://127.0.0.1:8000/health/live
docker exec dnd-vtt-redis-local redis-cli ping
```

Для функциональной проверки:

1. В приложении введите свою почту и запросите ссылку входа. На локальном Supabase письмо смотрите в ящике `54324`, а не в реальной почте.
2. Откройте ссылку в том же браузере. Создайте тестовую кампанию **после** успешного применения миграций.
3. Откройте стол, создайте сцену, загрузите небольшую PNG/JPEG-карту. Это проверяет Postgres и Storage, а не только HTTP health.
4. Добавьте карточку и токен, измените ресурс. Откройте гостевое приглашение в приватном окне того же Windows-ПК; проверьте синхронизацию перемещения.
5. Перезагрузите страницу: подтверждённая кампания и сцена должны сохраниться.

Локальный `health/ready` может вернуть `ok` даже при неполной конфигурации; исходник проверяет обязательность настроек только вне `local/test`. Успешный health не заменяет этот сценарий.

## 8. Остановить и затем запустить снова

В двух терминалах приложения нажмите `Ctrl+C`. Затем в корне проекта:

```bash
docker stop dnd-vtt-redis-local
npx supabase stop
```

Используйте обычный `stop`: не добавляйте `--no-backup`, не удаляйте Docker volumes. Для следующего запуска:

```bash
npx supabase start
npx supabase migration up --local
docker start dnd-vtt-redis-local
```

После этого снова откройте два терминала с `make dev-backend` и `make dev-frontend`. Повторная установка зависимостей и генерация JWT-ключа не нужны.

## 9. Что делать с существующим Docker Compose

`compose.yaml` содержит **Redis + API + Caddy/web**, но **не содержит Supabase Postgres/Auth/Storage**. Поэтому `docker compose up --build` в пустом checkout не является готовой установкой всей платформы.

Для первого локального запуска используйте путь выше. Если позже нужен именно контейнерный API/web, отдельно настройте доступный контейнеру и браузеру Supabase, БД и redirects/origins для `http://localhost:8080`; `VITE_*` передаются как build args и требуют пересборки web. В контейнере `127.0.0.1` означает сам контейнер, а не Windows/WSL-хост. Нельзя просто заменить только backend URL на `host.docker.internal`: verifier также выводит из него ожидаемый JWT issuer. В поставленном Caddy CSP разрешены внешние `https:`/`wss:`, но не HTTP-вызовы к локальному Supabase на другом origin. Контейнерный вариант требует отдельной согласованной сетевой конфигурации и здесь не заявляется проверенным.

## 10. Проверки разработчика

Для обычной локальной установки сперва выполните функциональный сценарий выше. Для тестов создаётся **отдельная новая** БД `vtt_ticket01`; не направляйте тесты на игровую `postgres`.

```bash
export VTT_TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:54322/vtt_ticket01'
export VTT_TEST_REDIS_URL='redis://127.0.0.1:6379/15'
.venv/bin/python scripts/acceptance_database.py --prepare-integration
make verify
```

Шаг `--prepare-integration` допустим только при отсутствии этой тестовой базы и откажется менять существующую. Если она уже подготовлена, этот шаг пропустите. `make verify` не допускает скрытых пропусков интеграционных тестов. `make test-e2e` / `make test-load` дополнительно требуют уже установленный **Linux** Playwright и Linux Chromium и явные пути `VTT_PLAYWRIGHT_MODULE` / `VTT_CHROME_EXECUTABLE`; Windows-путь к Chrome вместо Linux executable не подходит. Здесь эти проверки не заявляются успешно выполненными.

## 11. Частые ошибки

| Симптом | Что проверить |
| --- | --- |
| `make: command not found`, `.venv/bin/...` отсутствует | Команды выполняются в Ubuntu; установлен `make`; выполнен bootstrap с Python 3.13 |
| Python 3.12 или ошибка `requires-python` | `uv python find 3.13` и `.venv/bin/python --version`; системный Python Ubuntu 24.04 сам по себе не подходит |
| Docker `Cannot connect` / Windows containers | Docker Desktop запущен, Linux containers и WSL Integration включены |
| `address already in use` на 6379/54321/54322 | Сначала проверьте `docker ps` и `ss -ltn`; не останавливайте неизвестные контейнеры и не сбрасывайте БД |
| Долго скачиваются образы или пакеты | Первый старт требует сети; проверьте доступ к Docker registry/npm/PyPI и настройки proxy, не меняя lock-файлы |
| Интерфейс просит настроить авторизацию | Корневой `.env`, оба `VITE_SUPABASE_*`, перезапуск Vite |
| Письма нет в реальном почтовом ящике | Локальная почта находится по адресу `54324`; учитывайте лимит отправки в `supabase/config.toml` |
| После входа API возвращает 401 | Непустой JWKS с ES256/RS256; одинаковый Supabase URL и hostname; новый вход после изменения ключа; URL содержит `http://127.0.0.1:54321`, **без** `/auth/v1` на конце |
| `relation app.… does not exist` / bucket отсутствует | Все миграции применены к тому же DB URL, что указан у backend |
| Стол открывается, но соединение теряется | Redis отвечает `PONG`; API и Vite запущены; WebSocket идёт через `/api/.../realtime/ws`; origin находится в разрешённых |
| Карта не загружается | Приватный bucket `vtt-assets`, локальный service_role только на backend, допустимый формат и размер до 50 МиБ |
| Windows-браузер не видит приложение | В Ubuntu отвечает `curl http://127.0.0.1:5173`; в PowerShell выполните `Test-NetConnection 127.0.0.1 -Port 5173`; затем проверьте WSL networking, не отключая firewall целиком |
| Гостевая ссылка не открывается на другом ПК | `127.0.0.1` относится к компьютеру получателя. Для нескольких ПК нужны доступный обоим адрес, TLS, origins и Auth redirects; это отдельный сетевой этап |

Основа инструкции — файлы указанного коммита. Обновления внешних инструментов могут менять установку; используйте закреплённый CLI, проверяйте его `--help` и не считайте отсутствие Windows-проверки подтверждением совместимости.
