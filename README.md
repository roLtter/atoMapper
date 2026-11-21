# atoMapper

Готовит пары `reactant.xyz` / `product.xyz` к NEB в ORCA: одна нумерация атомов, отчёт по связям, 3D-превью.

## Режимы

### 1. Облако (polza.ai)

Нужен `POLZA_API_KEY`. Загружаются два XYZ → mapping через `polza.ai` → `reactant_mapped.xyz`, `product_mapped.xyz`, `mapping.json`, `report.md` + 3D.

### 2. Ручной

1. **Подготовка** — локально только нормализация (центр + главные оси). После подготовки доступно скачивание `reactant_norm.xyz`, `product_norm.xyz`, `prompt.txt`.
2. Отправляете их в свой чат GPT.
3. **Импорт** — загружаете полученные файлы `reactant_mapped.xyz`, `product_mapped.xyz`, `mapping.json` → визуализация подробного отчёта + 3D.

## Архитектура

```
frontend (React + Tailwind + Vite)
    │  /api/*
    ▼
backend (Go / Gin)  ──jobs──►  chem-worker (FastAPI / RDKit)
                                   │
                                   ├─ /map          polza.ai mapping
                                   ├─ /normalize    manual prep
                                   └─ /from-mapping import mapped files
```


| Часть | Стек |
|-------|------|
| `frontend/` | React, TypeScript, Tailwind v4, 3Dmol |
| `backend/` | Go, Gin |
| `chem-worker/` | Python, FastAPI, RDKit, numpy |
| LLM | только polza.ai (`POLZA_API_KEY`) |

## Быстрый старт

```powershell
copy .env.example .env
# задать POLZA_API_KEY=
# задать LLM_MODEL=

python -m venv .venv
.\.venv\Scripts\pip install -e ".\chem-worker[dev,api]"

.\.venv\Scripts\python -m uvicorn mapper.api:app --app-dir chem-worker --host 127.0.0.1 --port 8000

cd backend
go run ./cmd/server

cd ..\frontend
npm install
npm run dev
```

UI: `http://127.0.0.1:5173` · API: `:8080` · worker: `:8000`

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/api/jobs` | облачный mapping (`reactant`, `product`) |
| POST | `/api/jobs/normalize` | ручная подготовка |
| POST | `/api/jobs/from-mapping` | импорт (`reactant`, `product`, `mapping`) |
| GET | `/api/jobs/:id` | статус |
| GET | `/api/jobs/:id/files/:name` | артефакты |
| GET | `/api/llm` | модель / ключ polza |

## Тесты

```powershell
.\.venv\Scripts\python -m pytest chem-worker/tests -q
```

## Docker

Базовый стек (frontend + api + chem-worker), без Redis/MinIO:

```powershell
docker compose up --build
```

UI: http://localhost:3000

Redis/MinIO опционально (если Docker Hub доступен):

```powershell
docker compose --profile extras up --build
```
