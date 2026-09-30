# Журнал изменений

Каждая запись соответствует одному коммиту. Время — Asia/Qyzylorda (UTC+05:00).

## 2026-09-30 12:59:42 +05:00 — Приложение переименовано в Anamio; добавлен журнал изменений

Изменены: `AGENTS.md`, `README.md`, `backend/app/main.py`, `deploy/gpu/README.md`, `deploy/placeholder.html`, `frontend/index.html`, `frontend/src/App.vue`, `frontend/src/Auth.vue`, `frontend/src/UmcLogo.vue`, `scripts/commit.py`.

## 2026-09-30 13:07:19 +05:00 — Добавлен справочник МКБ-10 с поиском по кодам, сокращениям и опечаткам

Изменены: `backend/app/catalogs/README.md`, `backend/app/catalogs/icd10.ru.json`, `backend/app/diagnoses.py`, `backend/tests/test_diagnoses.py`.

## 2026-09-30 13:21:10 +05:00 — Добавлены автоматический анализ OpenAI, архив аудио и версий приёма, API МИС

Изменены: `.env.example`, `backend/app/config.py`, `backend/app/history.py`, `backend/app/main.py`, `backend/app/openai_asr.py`, `backend/app/openai_llm.py`, `backend/app/providers.py`, `backend/app/schemas.py`, `backend/app/worker.py`, `backend/tests/test_consultation_pipeline.py`, `backend/tests/test_openai_asr.py`, `backend/tests/test_openai_llm.py`, `backend/tests/test_workflow.py`.

## 2026-09-30 13:23:18 +05:00 — Исправлены остановка записи, пауза и ожидание разрешения микрофона

Изменены: `frontend/package.json`, `frontend/src/recorder.js`, `frontend/tests/recorder.test.js`.

## 2026-09-30 13:25:09 +05:00 — Обновлён лист консультации: загрузка аудио, источники полей, диагнозы и утверждение

Изменены: `frontend/src/App.vue`, `frontend/src/ClinicalField.vue`, `frontend/src/Consultation.vue`, `frontend/src/DiagnosisPicker.vue`, `frontend/src/Settings.vue`, `frontend/src/recorder.js`, `frontend/src/style.css`.

## 2026-09-30 13:27:04 +05:00 — Документированы новый конвейер, хранение записей и результаты сквозной проверки

Изменены: `README.md`, `docs/verification-2026-09-30.md`.

## 2026-09-30 13:31:52 +05:00 — Зафиксированы успешные проверки релиза на сервере и OpenAI API

Изменены: `docs/verification-2026-09-30.md`.

## 2026-09-30 13:35:16 +05:00 — Убраны лишние пояснения из README, упрощено описание приложения

Изменены: `README.md`.

## 2026-09-30 13:58:42 +05:00 — Добавлен PDF листа первичного и повторного приёма с логотипом UMC

Изменены: `backend/app/consultation_pdf.py`, `backend/assets/README.md`, `backend/assets/fonts/Inter-Bold.ttf`, `backend/assets/fonts/Inter-Regular.ttf`, `backend/assets/fonts/OFL.txt`, `backend/assets/umc-horizontal.png`, `backend/requirements.lock`, `backend/requirements.txt`, `backend/tests/test_consultation_pdf.py`.

## 2026-09-30 14:00:33 +05:00 — Добавлены общий поиск пациентов, этапы приёма и серверное окно записи 15 минут

Изменены: `backend/app/db.py`, `backend/app/history.py`, `backend/app/lifecycle.py`, `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/worker.py`, `backend/migrations/versions/0002_shared_patients_visit_lifecycle.py`, `backend/tests/audio_fixture.py`, `backend/tests/test_consultation_pipeline.py`, `backend/tests/test_migration.py`, `backend/tests/test_openai_asr.py`, `backend/tests/test_visit_lifecycle.py`, `backend/tests/test_workflow.py`.

## 2026-09-30 14:01:35 +05:00 — Оформлен Smart Consult в палитре UMC, добавлены общий поиск и мои приёмы

Изменены: `frontend/index.html`, `frontend/src/App.vue`, `frontend/src/Auth.vue`, `frontend/src/Settings.vue`, `frontend/src/UmcLogo.vue`, `frontend/src/assets/fonts/Inter-Variable.ttf`, `frontend/src/assets/fonts/OFL.txt`, `frontend/src/style.css`.

## 2026-09-30 14:03:50 +05:00 — Добавлены таймер, пауза, запись в разговоре и проверка листа консультации

Изменены: `frontend/src/App.vue`, `frontend/src/ClinicalField.vue`, `frontend/src/Consultation.vue`, `frontend/src/consultation.css`, `frontend/src/visit.js`, `frontend/tests/visit.test.js`.

## 2026-09-30 14:06:50 +05:00 — Стабилизирован документ МИС для безопасной повторной отправки

Изменены: `backend/app/main.py`, `backend/tests/test_mis_client.py`, `backend/tests/test_visit_lifecycle.py`, `backend/tests/test_workflow.py`, `examples/mis_client.py`.

## 2026-09-30 14:06:59 +05:00 — Добавлена резервная копия medhub перед серверными миграциями

Изменены: `deploy/backup-database.py`, `deploy/update-service-release.sh`.

## 2026-09-30 14:10:01 +05:00 — Описаны Smart Consult и результаты проверки всех 18 требований

Изменены: `README.md`, `docs/acceptance-2026-09-30-smart-consult.md`.

## 2026-09-30 14:14:15 +05:00 — Зафиксирована публикация Smart Consult и исправлен список файлов changelog

Изменены: `docs/acceptance-2026-09-30-smart-consult.md`, `scripts/commit.py`.

## 2026-09-30 14:33:01 +05:00 — Добавлены зашифрованный архив согласий и бланк пациента

Изменены: `backend/app/consent_document.py`, `backend/app/db.py`, `backend/migrations/versions/0003_patient_consent_signatures.py`.

## 2026-09-30 14:33:28 +05:00 — Реализованы проверка ЭЦП пациента через SIGEX и отзыв согласия

Изменены: `.env.example`, `backend/app/config.py`, `backend/app/consent.py`, `backend/app/consent_sigex.py`, `backend/app/main.py`, `backend/app/worker.py`, `backend/tests/conftest.py`, `backend/tests/test_consent_policy.py`, `backend/tests/test_patient_consents.py`.

## 2026-09-30 14:33:33 +05:00 — Добавлены подписание согласия по QR и NCALayer и статус ЭЦП в карте

Изменены: `frontend/src/App.vue`, `frontend/src/ConsentSigning.vue`, `frontend/src/eds.js`, `frontend/tests/eds.test.js`.

## 2026-09-30 14:35:49 +05:00 — Описаны процедура согласия пациента и результаты проверок ЭЦП

Изменены: `README.md`, `docs/sigex-patient-consent.md`, `docs/verification-2026-09-30-consent.md`.

## 2026-09-30 14:38:39 +05:00 — Зафиксирована проверка серверного релиза согласий пациента

Изменены: `docs/verification-2026-09-30-consent.md`.

## 2026-09-30 14:40:40 +05:00 — Закреплены обязательные коммит, push и деплой после каждой задачи

Изменены: `AGENTS.md`.

## 2026-09-30 14:55:18 +05:00 — Разделены ИИ-подсказки и результат врача, сохранены заполненные поля при анализе

Изменены: `backend/app/clinical.py`, `backend/app/consultation_pdf.py`, `backend/app/main.py`, `backend/app/providers.py`, `backend/app/schemas.py`, `backend/app/worker.py`, `backend/tests/test_clinical_merge.py`, `backend/tests/test_consultation_pdf.py`, `backend/tests/test_consultation_pipeline.py`, `backend/tests/test_openai_llm.py`, `backend/tests/test_providers.py`, `backend/tests/test_workflow.py`.

## 2026-09-30 14:55:29 +05:00 — Развёрнута форма приёма на всю ширину, итог перенесён вниз, расшифровка свёрнута

Изменены: `README.md`, `docs/verification-2026-09-30-ai-advisory.md`, `frontend/src/Consultation.vue`, `frontend/src/consultation.css`.

## 2026-09-30 15:12:31 +05:00 — Добавлены нормализация реквизитов и повторный анализ с учётом правок врача

Изменены: `backend/app/clinical.py`, `backend/app/main.py`, `backend/app/patient_input.py`, `backend/app/privacy.py`, `backend/app/providers.py`, `backend/app/schemas.py`, `backend/app/worker.py`, `backend/tests/test_clinical_merge.py`, `backend/tests/test_consultation_pipeline.py`, `backend/tests/test_patient_input.py`, `backend/tests/test_regeneration.py`, `backend/tests/test_workflow.py`.
