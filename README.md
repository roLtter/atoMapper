# atom-mapper

Готовит геометрии к NEB в ORCA. На вход: `reactant.xyz` и `product.xyz`
(один состав, разный порядок атомов, продукт может быть повёрнут или сдвинут).
На выход: два `.xyz` с одной нумерацией и короткий report.

Без общей нумерации NEB тянет «не те» атомы друг к другу.

Позы только нормализуются (центр + главные оси). Сам mapping делает LLM
(по умолчанию локальный Bonsai через Ollama). Дальше проверка биекции/элементов,
сравнение с алгоритмическим baseline и Kabsch.

## Стек

| Часть | Что |
|-------|-----|
| `backend/` | Go, Gin |
| `chem-worker/` | Python, FastAPI, RDKit, numpy |
| `frontend/` | React, TypeScript, Tailwind |
| Инфра | Redis, MinIO, docker compose |
| LLM | Ollama (`bonsai-mapper`) или OpenRouter |

Секретов в репо нет. Скопируй `.env.example` в `.env`.

Подробнее про коммиты, Bonsai и fallback: [NOTES.md](NOTES.md).

## Ollama (локально)

Нужен Ollama >= 0.40.6. На 12 GB VRAM держи `num_ctx=8192`.

```powershell
ollama create bonsai-mapper -f ops/Modelfile.bonsai-mapper
# или FROM на свой GGUF, см. NOTES.md
```

В `.env`: `LLM_PROVIDER=ollama`, `LLM_MODEL=bonsai-mapper`.

## Локальная разработка

```bash
python -m venv .venv
.\.venv\Scripts\pip install -e ".\chem-worker[dev,api]"

.\.venv\Scripts\python -m pytest chem-worker/tests
.\.venv\Scripts\python -m mapper

cd backend
go run ./cmd/server

cd ../frontend
npm install
npm run dev
```

Без сервисов:

```bash
cd chem-worker
python -c "from mapper import map_atoms; map_atoms('a.xyz','b.xyz', out_dir='out')"
```

## Docker

```bash
docker compose up --build
```

UI `http://localhost:3000`, API `http://localhost:8080`, chem-worker `http://localhost:8000`.

## API

- `POST /api/jobs` multipart: `reactant`, `product`, опционально `charge`, `multiplicity`, `model`, `use_llm`
- `GET /api/jobs/:id`
- `GET /api/jobs/:id/files/...` (`reactant_mapped.xyz`, `product_mapped.xyz`, `mapping.json`, `report.md`)
