# Журнал изменений

Каждая запись соответствует одному коммиту. Время — Asia/Qyzylorda (UTC+05:00).

## 2026-09-30 12:59:42 +05:00 — Приложение переименовано в Anamio; добавлен журнал изменений

Изменены: `AGENTS.md`, `README.md`, `backend/app/main.py`, `deploy/gpu/README.md`, `deploy/placeholder.html`, `frontend/index.html`, `frontend/src/App.vue`, `frontend/src/Auth.vue`, `frontend/src/UmcLogo.vue`, `scripts/commit.py`, ``.

## 2026-09-30 13:07:19 +05:00 — Добавлен справочник МКБ-10 с поиском по кодам, сокращениям и опечаткам

Изменены: `backend/app/catalogs/README.md`, `backend/app/catalogs/icd10.ru.json`, `backend/app/diagnoses.py`, `backend/tests/test_diagnoses.py`, ``.

## 2026-09-30 13:21:10 +05:00 — Добавлены автоматический анализ OpenAI, архив аудио и версий приёма, API МИС

Изменены: `.env.example`, `backend/app/config.py`, `backend/app/history.py`, `backend/app/main.py`, `backend/app/openai_asr.py`, `backend/app/openai_llm.py`, `backend/app/providers.py`, `backend/app/schemas.py`, `backend/app/worker.py`, `backend/tests/test_consultation_pipeline.py`, `backend/tests/test_openai_asr.py`, `backend/tests/test_openai_llm.py`, `backend/tests/test_workflow.py`, ``.

## 2026-09-30 13:23:18 +05:00 — Исправлены остановка записи, пауза и ожидание разрешения микрофона

Изменены: `frontend/package.json`, `frontend/src/recorder.js`, `frontend/tests/recorder.test.js`, ``.

## 2026-09-30 13:25:09 +05:00 — Обновлён лист консультации: загрузка аудио, источники полей, диагнозы и утверждение

Изменены: `frontend/src/App.vue`, `frontend/src/ClinicalField.vue`, `frontend/src/Consultation.vue`, `frontend/src/DiagnosisPicker.vue`, `frontend/src/Settings.vue`, `frontend/src/recorder.js`, `frontend/src/style.css`, ``.
