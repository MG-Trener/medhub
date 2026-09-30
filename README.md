# Anamio

Anamio — кабинет врача и AI-ассистент для заполнения листа консультации. Создано в рамках хакатона medhub.

Стек: Vue 3, FastAPI, PostgreSQL, Docker Compose.

## Возможности

- Регистрация и вход по паролю, ЭЦП через NCALayer + SIGEX, QR через eGov Mobile.
- Карточки пациентов с ИИН, поиск по ФИО и ИИН, история приёмов.
- Запись разговора с выбором микрофона, паузой и продолжением; загрузка WAV, MP3, M4A, MP4, WebM, OGG и FLAC до 80 МБ.
- Распознавание речи с таймкодами и разделением голосов, определение ролей врача, пациента и медсестры.
- Заполнение жалоб, анамнеза, аллергий, лекарств, результатов осмотра, исследований, назначений и плана наблюдения.
- Поиск диагнозов по коду, названию, сокращениям и близкому написанию в справочнике МКБ-10; предложения ИИ для проверки врачом. [Источник справочника](backend/app/catalogs/README.md).
- Ссылки заполненных полей на реплики, редактирование и утверждение результата врачом.
- Зашифрованный архив аудио, расшифровок, заключений и истории изменений.
- API для МИС и пример клиента отправки утверждённых консультаций.

## Сценарий приёма

1. Найдите пациента или создайте карточку, зафиксируйте согласия.
2. Нажмите «Начать приём» и запишите разговор либо загрузите готовую запись.
3. «Закончить диалог приёма» запускает распознавание, маскирование текста и заполнение листа. Для загруженного файла нажмите «Распознать и заполнить».
4. Проверьте расшифровку, роли, диагноз и поля консультации; внесите исправления.
5. Утвердите результат — он станет доступен через API МИС.

Без согласия на запись лист заполняется вручную. Предварительное заключение ИИ не является диагнозом; окончательное решение и ответственность остаются за врачом.

## Локальный запуск

Нужен Docker Desktop с Linux containers.

```powershell
./scripts/setup.ps1
docker compose up --build -d
```

- Интерфейс: http://localhost:5173
- OpenAPI / Swagger: http://localhost:5173/api/docs
- API: http://localhost:8010

`setup.ps1` создаёт `.env` с ключами шифрования, паролем PostgreSQL и кодом приглашения. Существующий файл не перезаписывается. Для регистрации врача используйте `REGISTRATION_CODE`.

Для демонстрационного окружения:

```powershell
./scripts/setup.ps1 -Demo
docker compose up --build -d
docker compose exec api python -m app.seed_demo
```

Логин: `doctor@medhub.local`. Пароль — `DEMO_PASSWORD` из `.env`. Если файл уже существует, установите `DEMO_MODE=true`, задайте пароль длиной от 12 символов и пересоздайте API/worker перед первым запуском seed. Повторный seed не меняет пароль существующего кабинета.

Для разработки интерфейса:

```powershell
docker compose stop ui
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Vite перенаправляет `/api` на `127.0.0.1:8010`.

## Настройка OpenAI

В `.env` задайте:

```dotenv
ASR_PROVIDER=openai
OPENAI_API_KEY=<ключ проекта OpenAI API>
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-astra
LLM_IS_CLOUD=true
AUDIO_RETENTION_HOURS=0
```

Примените настройки:

```powershell
docker compose up -d --force-recreate --no-deps api worker
```

ASR использует `gpt-4o-transcribe-diarize`, LLM — Responses API со строгой JSON-схемой и `store=false`. Один серверный `OPENAI_API_KEY` используется для обоих вызовов. Ключи хранятся в конфигурации окружения и не передаются во Vue или Git.

Для обработки нужны согласия на запись, передачу исходного аудио в OpenAI и анализ обезличенного текста облачной LLM. Маскирование текста выполняется после распознавания: исходное аудио отправляется в OpenAI до маскирования.

Перед отправкой ffmpeg сжимает аудио в mono MP3. Лимит после сжатия — 24 MB. Исходная запись, маскированная копия и результаты остаются в зашифрованном архиве. При сбое LLM расшифровка сохраняется; анализ можно повторить отдельно.

Документация: [распознавание речи](https://developers.openai.com/api/docs/guides/speech-to-text), [модель с диаризацией](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize).

## Собственные модели

Инструкция по настройке удалённого GPU-ПК и отдельный Compose: [deploy/gpu/README.md](deploy/gpu/README.md).

```dotenv
ASR_PROVIDER=self_hosted
ASR_URL=http://<VPN-IP-GPU-ПК>:8090
ASR_API_KEY=<ASR_SERVICE_TOKEN>
INSTALL_LOCAL_AI=false
LLM_PROVIDER=ollama
LLM_URL=http://<VPN-IP-GPU-ПК>:11434
LLM_MODEL=qwen3:8b
LLM_IS_CLOUD=false
```

Для другого облачного провайдера с OpenAI-совместимым API:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_URL=https://<провайдер>/v1
LLM_API_KEY=<ключ>
LLM_MODEL=<модель с JSON-output>
LLM_IS_CLOUD=true
```

## Данные и доступ

Медицинские тексты, карточки и аудио шифруются на уровне приложения. Поиск использует HMAC-индексы, пароли — Argon2, сессии — HttpOnly-cookie. Служебные идентификаторы, связи, времена и статусы хранятся отдельно. Сохраняйте `ENCRYPTION_KEY` и `INDEX_KEY` вместе с защищённой резервной копией конфигурации: они нужны для восстановления данных.

Автоматическое маскирование заменяет найденные ФИО, ИИН, контакты и адреса маркерами. Врач проверяет результат во вкладке «Маскирование» и может заглушить дополнительные реплики в копии аудио. Маскирование не гарантирует удаления всех персональных данных.

Архив хранится без автоматического удаления. Отзыв согласия блокирует новую запись и соответствующую облачную обработку, сохраняя ранее созданный архив. Доступ к данным ограничен кабинетом врача; МИС получает только утверждённые приёмы по ключу этого врача. Действия фиксируются в журнале аудита.

## ЭЦП и eGov Mobile

При регистрации указывается ИИН врача. SIGEX проверяет подпись и возвращает подтверждённый ИИН, по которому Anamio находит учётную запись. При регистрации по подписи ИИН формы должен совпадать с ИИН владельца ЭЦП.

Для ЭЦП нужны NCALayer и действующий ключ, для QR — eGov Mobile. Ранее созданный кабинет без ИИН можно привязать через «Настройки → ИИН и вход по ЭЦП».

Документация интеграции: [SIGEX auth](https://sigex.kz/support/developers/api-auth/), [SIGEX eGov QR](https://sigex.kz/support/developers/api-egov-basic/).

## API МИС

Создайте ключ во вкладке «Настройки» и передавайте его в `Authorization: Bearer <ключ>`. Ключ показывается один раз; новый выпуск отзывает предыдущий.

| Метод | URL | Назначение |
|---|---|---|
| GET | `/api/v1/integration/encounters?since=0&offset=0&limit=50` | Утверждённые приёмы; `since` — Unix-время утверждения |
| GET | `/api/v1/integration/encounters?patient_id=<UUID>` | Приёмы пациента |
| GET | `/api/v1/integration/encounters/{UUID}` | Карточка пациента, поля листа, расшифровка и роли |
| GET | `/api/v1/integration/encounters/{UUID}/recordings` | Архив записей с расшифровками и ролями |
| GET | `/api/v1/integration/encounters/{UUID}/recordings/{recording_id}/audio` | Исходное аудио |
| POST | `/api/v1/encounters/{UUID}/send-to-mis` | Отправка в МИС; сессия врача и `{ "version": N }` |

Ответ списка содержит `items` и `next_offset`. Формат документа — `schema_version=1.1`; `recordings_url` указывает на архив аудио. UUID и `version` определяют версию приёма. После редактирования требуется повторное утверждение.

Исходящий запрос использует `Idempotency-Key: <UUID>:<version>`. Для кнопки «Отправить в МИС» задайте `MIS_URL` и `MIS_TOKEN` в конфигурации backend.

Пример приёмника: [examples/mock_mis.py](examples/mock_mis.py). Он хранит контрольные суммы в памяти. Пример клиента: [examples/mis_client.py](examples/mis_client.py).

```powershell
# MIS_TOKEN задайте через окружение.
python -m uvicorn examples.mock_mis:app --host 127.0.0.1 --port 8020 --no-access-log
```

Клиент использует `MEDHUB_API_KEY`, `MIS_TOKEN`, `MEDHUB_URL` и `MIS_URL` из окружения. Адреса по умолчанию: `http://localhost:8010` и `http://localhost:8020/v1/consultations`.

```powershell
python examples/mis_client.py <UUID-подтверждённого-приёма>
```

В обоих направлениях интеграции передаётся `encounter.ai_notice` с пометкой, что заключение ИИ не является диагнозом и требует проверки врачом.

## Развёртывание

Docker Compose: [compose.yaml](compose.yaml), [конфигурация production](deploy/compose.production.yaml).

На [medhub.ych.kz](https://medhub.ych.kz/) приложение работает через systemd:

- Активный релиз: `/opt/medhub/current`.
- Интерфейс: `/opt/medhub/current/ui`, отдаётся Nginx по HTTPS.
- Службы: `medhub-api` и `medhub-worker`.
- Конфигурация: `/opt/medhub/shared/app.env`, права `600`.
- Аудио: `/opt/medhub/shared/audio`.

```sh
systemctl status medhub-api medhub-worker
systemctl restart medhub-api medhub-worker
curl --fail https://medhub.ych.kz/api/health
```

Первичная установка: [deploy/install-service-release.sh](deploy/install-service-release.sh). Обновление после загрузки исходников и собранного UI в каталог релиза:

```sh
sh deploy/update-service-release.sh <release-id>
```

Скрипт сохраняет настройки и возвращает предыдущий релиз при неудачном запуске. Миграции данных автоматически не откатываются. Файлы служб: [deploy/systemd](deploy/systemd); Nginx: [deploy/nginx/medhub.https.conf](deploy/nginx/medhub.https.conf).

## Проверки и изменения

```powershell
cd backend
python -m pytest -q
cd ../frontend
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

[Протокол проверки](docs/verification-2026-09-30.md) · [Журнал изменений](CHANGELOG.md)
