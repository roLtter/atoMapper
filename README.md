# atom-mapper

Сервис для подготовки геометрий к NEB в ORCA: на входе `reactant.xyz` и `product.xyz`
(одинаковый состав, разный порядок атомов, продукт может быть повёрнут или сдвинут),
на выходе два `.xyz` с согласованной нумерацией и отчёт, как выбирался маппинг.

Без согласованной нумерации NEB интерполирует «не те» атомы.

Алгоритм строит кандидатов маппинга, локальная LLM оценивает их химически,
детерминированный верификатор отсекает плохие ответы модели.

## Стек

| Часть | Технологии |
|-------|------------|
| `backend/` | Go, Gin — API, очередь задач, файлы |
| `chem-worker/` | Python, FastAPI, RDKit, numpy, scipy, networkx — химия и LLM |
| `frontend/` | React, TypeScript, Tailwind |
| Инфра | Redis, MinIO, docker compose |
| LLM | Ollama на хосте (`http://host.docker.internal:11434` из контейнеров) |

Модели задаются через env (`LLM_BASE_URL`, `LLM_MODEL`, …), секретов в репозитории нет.
Для разработки — `neb-fast` (qwen3:8b), основная — `neb-main` (14B-класс).
Modelfile-ы лежат в `ops/`.

```bash
ollama create neb-fast -f ops/Modelfile.neb-fast
ollama create neb-main -f ops/Modelfile.neb-main
ollama list
ollama ps
ollama stop neb-fast
```

Сравнение моделей на фикстурах (Ollama должна быть запущена):

```bash
cd chem-worker
python -m mapper.bench --model neb-fast
python -m mapper.bench --no-llm
```

## Локальная разработка

```bash
python -m venv .venv
.\.venv\Scripts\pip install -e ".\chem-worker[dev,api]"

# chem-worker
.\.venv\Scripts\python -m pytest chem-worker/tests
.\.venv\Scripts\python -m mapper

# backend
cd backend
go run ./cmd/server

# frontend
cd ../frontend
npm install
npm run dev
```

Python-маппинг без сервиса (из `chem-worker/` с `PYTHONPATH=.`):

```bash
python -c "from mapper import map_atoms; map_atoms('a.xyz','b.xyz', out_dir='out')"
```

## Docker

```bash
docker compose up --build
```

UI: `http://localhost:3000` · API: `http://localhost:8080` · chem-worker: `http://localhost:8000`

Скопируйте `.env.example` при необходимости. Ollama остаётся на хосте.

## API

- `POST /api/jobs` — multipart: `reactant`, `product`, опционально `charge`, `multiplicity`, `model`, `use_llm`
- `GET /api/jobs/:id` — статус и шаг
- `GET /api/jobs/:id/files/...` — `reactant_mapped.xyz`, `product_mapped.xyz`, `mapping.json`, `report.md`
