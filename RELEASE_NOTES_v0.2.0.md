# atoMapper v0.2.0

Два режима: polza.ai по `POLZA_API_KEY` и ручной (normalize → свой чат → импорт).

## Что нового

### Облако (polza.ai)

- Единственный LLM-провайдер: polza.ai, модель `openai/gpt-5.6-sol`
- Локальный Ollama/Bonsai, OpenRouter/Gemini и алго-fallback убраны
- Verifier: биекция + совпадение элементов

### Ручной режим

1. Нормализация геометрий без mapping
2. Скачивание `reactant_norm.xyz`, `product_norm.xyz`, `prompt.txt`
3. Импорт ответа модели → отчёт и 3D

### UI / DX

- Переключатель режимов
- Без полей заряда / мультиплетности
- Tailwind CSS v4

## API

- `POST /api/jobs` — облако
- `POST /api/jobs/normalize` — подготовка
- `POST /api/jobs/from-mapping` — импорт
- `GET /api/llm` — статус polza

## Breaking changes

- Только `POLZA_API_KEY` (нет Ollama / openrouter / gemini)
- Нет `mapper.bench --no-llm` и алго-oracle CI-пути
- Нет UI/API `charge` / `multiplicity`

## Миграция

1. `.env.example` → `.env`
2. Задайте `POLZA_API_KEY`
3. Удалите старые `LLM_PROVIDER=ollama` / ключи OpenRouter/Gemini

## Проверки

- `pytest chem-worker/tests`
- `go build ./cmd/server`
- `npm run build` в `frontend/`
