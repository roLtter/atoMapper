# atom-mapper

Сервис для подготовки геометрий к NEB в ORCA: на входе `reactant.xyz` и `product.xyz`
(одинаковый состав, разный порядок атомов, продукт может быть повёрнут или сдвинут),
на выходе два `.xyz` с согласованной нумерацией и отчёт, как выбирался маппинг.

Без согласованной нумерации NEB интерполирует «не те» атомы.

Алгоритм строит кандидатов маппинга, локальная LLM оценивает их химически,
детерминированный верификатор отсекает плохие ответы модели.

## Стек


| Часть          | Технологии                                                           |
| -------------- | -------------------------------------------------------------------- |
| `backend/`     | Go, Gin — API, очередь задач, файлы                                  |
| `chem-worker/` | Python, FastAPI, RDKit, numpy, scipy, networkx - химия и LLM         |
| `frontend/`    | React, TypeScript, Tailwind                                          |
| Инфра          | Redis, MinIO, docker compose                                         |
| LLM            | Ollama на хосте (`http://host.docker.internal:11434` из контейнеров) |


Модели задаются через env (`LLM_BASE_URL`, `LLM_MODEL`, …), секретов в репозитории нет. Для разработки - `neb-fast` (qwen3:8b), основная - `neb-main` (14B-класс).
Modelfile-ы лежат в `ops/`.

## Запуск

Пока репозиторий в ранней стадии. Целевой сценарий:

1. Поднять Ollama на хосте и создать модели из `ops/Modelfile.*`
2. `docker compose up` - API, Redis, MinIO, chem-worker, UI
3. Загрузить пару `.xyz` в UI или через `POST /api/jobs`

Детали compose и env появятся вместе со стеком.

## API (план)

- `POST /api/jobs` - multipart: `reactant`, `product`
- `GET /api/jobs/:id` - статус и текущий шаг
- `GET /api/jobs/:id/files/...` - `reactant_mapped.xyz`, `product_mapped.xyz`, `mapping.json`, `report.md`

