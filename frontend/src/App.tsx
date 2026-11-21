import { useEffect, useMemo, useState } from 'react'
import { MoleculeViewer } from './MoleculeViewer'
import { ReportView } from './ReportView'

type Mode = 'cloud' | 'manual'
type ManualStep = 'prep' | 'import'

type Job = {
  job_id: string
  status: string
  step: string
  kind?: string
  error?: string
}

const CLOUD_FILES = [
  'reactant_mapped.xyz',
  'product_mapped.xyz',
  'mapping.json',
  'report.md',
] as const

const PREP_FILES = ['reactant_norm.xyz', 'product_norm.xyz', 'prompt.txt', 'report.md'] as const

function pickFile(files: FileList | null, ext: RegExp): File | null {
  if (!files?.length) return null
  const list = Array.from(files)
  return list.find((f) => ext.test(f.name)) ?? list[0] ?? null
}

async function downloadNamed(jobId: string, name: string) {
  const res = await fetch(`/api/jobs/${jobId}/files/${name}`)
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [mode, setMode] = useState<Mode>('cloud')
  const [manualStep, setManualStep] = useState<ManualStep>('prep')
  const [reactant, setReactant] = useState<File | null>(null)
  const [product, setProduct] = useState<File | null>(null)
  const [mappedReactant, setMappedReactant] = useState<File | null>(null)
  const [mappedProduct, setMappedProduct] = useState<File | null>(null)
  const [mappingJson, setMappingJson] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [report, setReport] = useState('')
  const [reactantXyz, setReactantXyz] = useState('')
  const [productXyz, setProductXyz] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [llmInfo, setLlmInfo] = useState('')

  const canCloud = useMemo(() => !!reactant && !!product && !busy, [reactant, product, busy])
  const canImport = useMemo(
    () => !!mappedReactant && !!mappedProduct && !!mappingJson && !busy,
    [mappedReactant, mappedProduct, mappingJson, busy],
  )
  const done = job?.status === 'done' && !!jobId
  const isPrepJob = job?.kind === 'normalize' || (done && manualStep === 'prep' && mode === 'manual')
  const showMappedView =
    done &&
    (mode === 'cloud' || (mode === 'manual' && manualStep === 'import')) &&
    (!!reactantXyz || !!productXyz)

  useEffect(() => {
    fetch('/api/llm')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return
        const key = data.api_key_set ? 'ключ задан' : `нет ключа (${data.api_key_env})`
        setLlmInfo(`${data.provider} · ${data.model} · ${key}`)
      })
      .catch(() => setLlmInfo(''))
  }, [])

  useEffect(() => {
    if (!jobId) return
    let stop = false
    const tick = async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`)
        if (!res.ok) throw new Error(await res.text())
        const data = (await res.json()) as Job
        if (stop) return
        setJob(data)
        if (data.status === 'done') {
          const kind = data.kind || (mode === 'manual' && manualStep === 'prep' ? 'normalize' : 'map')
          if (kind === 'normalize') {
            const reportRes = await fetch(`/api/jobs/${jobId}/files/report.md`)
            if (reportRes.ok) setReport(await reportRes.text())
          } else {
            const [reportRes, rXyz, pXyz] = await Promise.all([
              fetch(`/api/jobs/${jobId}/files/report.md`),
              fetch(`/api/jobs/${jobId}/files/reactant_mapped.xyz`),
              fetch(`/api/jobs/${jobId}/files/product_mapped.xyz`),
            ])
            if (reportRes.ok) setReport(await reportRes.text())
            if (rXyz.ok) setReactantXyz(await rXyz.text())
            if (pXyz.ok) setProductXyz(await pXyz.text())
          }
          setBusy(false)
          return
        }
        if (data.status === 'failed') {
          setError(data.error || 'ошибка задачи')
          setBusy(false)
          return
        }
        window.setTimeout(tick, 1000)
      } catch (e) {
        if (!stop) {
          setError(e instanceof Error ? e.message : String(e))
          setBusy(false)
        }
      }
    }
    tick()
    return () => {
      stop = true
    }
  }, [jobId, mode, manualStep])

  function resetResult() {
    setBusy(true)
    setError('')
    setReport('')
    setReactantXyz('')
    setProductXyz('')
    setJob(null)
    setJobId(null)
  }

  async function postJob(url: string, body: FormData) {
    resetResult()
    try {
      const res = await fetch(url, { method: 'POST', body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || res.statusText)
      setJobId(data.job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  async function onCloudSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reactant || !product) return
    const body = new FormData()
    body.append('reactant', reactant)
    body.append('product', product)
    await postJob('/api/jobs', body)
  }

  async function onPrepSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reactant || !product) return
    const body = new FormData()
    body.append('reactant', reactant)
    body.append('product', product)
    await postJob('/api/jobs/normalize', body)
  }

  async function onImportSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!mappedReactant || !mappedProduct || !mappingJson) return
    const body = new FormData()
    body.append('reactant', mappedReactant)
    body.append('product', mappedProduct)
    body.append('mapping', mappingJson)
    await postJob('/api/jobs/from-mapping', body)
  }

  async function downloadCloud() {
    if (!jobId) return
    for (const name of ['reactant_mapped.xyz', 'product_mapped.xyz'] as const) {
      await downloadNamed(jobId, name)
      await new Promise((r) => setTimeout(r, 150))
    }
  }

  async function downloadPrep() {
    if (!jobId) return
    for (const name of ['reactant_norm.xyz', 'product_norm.xyz', 'prompt.txt'] as const) {
      await downloadNamed(jobId, name)
      await new Promise((r) => setTimeout(r, 150))
    }
  }

  const statusLabel =
    job?.status === 'done'
      ? 'готово'
      : job?.status === 'failed'
        ? 'ошибка'
        : job?.status === 'running'
          ? 'считается'
          : job?.status ?? ''

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-4 py-10">
      <header className="space-y-2">
        <p className="text-sm tracking-[0.18em] text-muted uppercase">NEB PREP</p>
        <h1 className="font-serif text-4xl tracking-tight text-ink md:text-5xl">atoMapper</h1>
        <p className="max-w-2xl text-muted">
          Два режима: облачный mapping через polza.ai или ручная подготовка файлов для своего чата
          GPT.
        </p>
        {llmInfo && <p className="font-mono text-xs text-muted">{llmInfo}</p>}
      </header>

      <div className="grid gap-2 sm:grid-cols-2">
        <ModeCard
          active={mode === 'cloud'}
          title="Облако (polza.ai)"
          text="API-ключ → GPT-класс модель сопоставляет атомы за пару минут."
          onClick={() => {
            setMode('cloud')
            setError('')
          }}
        />
        <ModeCard
          active={mode === 'manual'}
          title="Ручной режим"
          text="Нормализация без mapping → скачать промпт и xyz → загрузить ответ модели."
          onClick={() => {
            setMode('manual')
            setError('')
          }}
        />
      </div>

      {mode === 'cloud' && (
        <form
          onSubmit={onCloudSubmit}
          className="grid gap-6 rounded-2xl border border-line bg-panel/90 p-6 shadow-sm md:grid-cols-2"
        >
          <Dropzone label="Реагент" file={reactant} onFile={setReactant} accept="xyz" />
          <Dropzone label="Продукт" file={product} onFile={setProduct} accept="xyz" />
          <button
            type="submit"
            disabled={!canCloud}
            className="rounded-xl bg-accent px-4 py-3 font-semibold text-accent-ink disabled:opacity-40 md:col-span-2"
          >
            {busy ? 'Считаем…' : 'Сопоставить через polza.ai'}
          </button>
        </form>
      )}

      {mode === 'manual' && (
        <section className="space-y-6 rounded-2xl border border-line bg-panel/90 p-6 shadow-sm">
          <div className="flex flex-wrap gap-2">
            <StepChip
              active={manualStep === 'prep'}
              label="1. Подготовка"
              onClick={() => setManualStep('prep')}
            />
            <StepChip
              active={manualStep === 'import'}
              label="2. Импорт ответа"
              onClick={() => setManualStep('import')}
            />
          </div>

          {manualStep === 'prep' ? (
            <form onSubmit={onPrepSubmit} className="grid gap-6 md:grid-cols-2">
              <p className="text-sm text-muted md:col-span-2">
                Алгоритм только нормализует геометрии (центр + главные оси). Mapping не делается —
                скачайте два `.xyz` и `prompt.txt`, отправьте в свой чат GPT.
              </p>
              <Dropzone label="Реагент" file={reactant} onFile={setReactant} accept="xyz" />
              <Dropzone label="Продукт" file={product} onFile={setProduct} accept="xyz" />
              <button
                type="submit"
                disabled={!canCloud}
                className="rounded-xl bg-accent px-4 py-3 font-semibold text-accent-ink disabled:opacity-40 md:col-span-2"
              >
                {busy ? 'Готовим…' : 'Нормализовать и выдать промпт'}
              </button>
            </form>
          ) : (
            <form onSubmit={onImportSubmit} className="grid gap-6 md:grid-cols-2">
              <p className="text-sm text-muted md:col-span-2">
                Загрузите три файла ответа модели: `reactant_mapped.xyz`, `product_mapped.xyz` и
                `mapping.json` — получите отчёт и 3D.
              </p>
              <Dropzone
                label="reactant_mapped.xyz"
                file={mappedReactant}
                onFile={setMappedReactant}
                accept="xyz"
              />
              <Dropzone
                label="product_mapped.xyz"
                file={mappedProduct}
                onFile={setMappedProduct}
                accept="xyz"
              />
              <div className="md:col-span-2">
                <Dropzone
                  label="mapping.json"
                  file={mappingJson}
                  onFile={setMappingJson}
                  accept="json"
                />
              </div>
              <button
                type="submit"
                disabled={!canImport}
                className="rounded-xl bg-accent px-4 py-3 font-semibold text-accent-ink disabled:opacity-40 md:col-span-2"
              >
                {busy ? 'Собираем отчёт…' : 'Построить отчёт и 3D'}
              </button>
            </form>
          )}
        </section>
      )}

      {(job || error) && (
        <section className="space-y-3 rounded-2xl border border-line bg-panel/90 p-6">
          <h2 className="text-xl font-semibold">Статус</h2>
          {job && (
            <p className="font-mono text-sm text-muted">
              {job.job_id} · {statusLabel}
              {job.step ? ` · ${job.step}` : ''}
              {job.kind ? ` · ${job.kind}` : ''}
            </p>
          )}
          {error && <p className="text-sm text-red-700">{error}</p>}
          {done && mode === 'cloud' && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={downloadCloud}
                className="rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-ink"
              >
                Скачать готовые файлы
              </button>
              {CLOUD_FILES.filter((n) => n === 'mapping.json' || n === 'report.md').map((name) => (
                <a
                  key={name}
                  className="rounded-lg border border-line bg-white px-3 py-2 text-sm hover:bg-accent-soft"
                  href={`/api/jobs/${jobId}/files/${name}`}
                  download
                >
                  {name}
                </a>
              ))}
            </div>
          )}
          {done && mode === 'manual' && manualStep === 'prep' && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={downloadPrep}
                className="rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-ink"
              >
                Скачать norm xyz + prompt
              </button>
              {PREP_FILES.map((name) => (
                <a
                  key={name}
                  className="rounded-lg border border-line bg-white px-3 py-2 text-sm hover:bg-accent-soft"
                  href={`/api/jobs/${jobId}/files/${name}`}
                  download
                >
                  {name}
                </a>
              ))}
              <button
                type="button"
                onClick={() => setManualStep('import')}
                className="rounded-lg border border-line bg-white px-3 py-2 text-sm hover:bg-accent-soft"
              >
                Перейти к импорту ответа →
              </button>
            </div>
          )}
          {done && mode === 'manual' && manualStep === 'import' && (
            <div className="flex flex-wrap items-center gap-2">
              {CLOUD_FILES.map((name) => (
                <a
                  key={name}
                  className="rounded-lg border border-line bg-white px-3 py-2 text-sm hover:bg-accent-soft"
                  href={`/api/jobs/${jobId}/files/${name}`}
                  download
                >
                  {name}
                </a>
              ))}
            </div>
          )}
        </section>
      )}

      {showMappedView && (
        <section className="space-y-4 rounded-2xl border border-line bg-panel/90 p-6">
          <h2 className="text-xl font-semibold">Согласованные структуры</h2>
          <div className="grid min-w-0 gap-6 md:grid-cols-2">
            {reactantXyz ? (
              <MoleculeViewer title="Реагент (согласованный)" xyz={reactantXyz} />
            ) : (
              <p className="text-sm text-muted">Файл реагента недоступен</p>
            )}
            {productXyz ? (
              <MoleculeViewer title="Продукт (согласованный)" xyz={productXyz} />
            ) : (
              <p className="text-sm text-muted">Файл продукта недоступен</p>
            )}
          </div>
        </section>
      )}

      {report && !isPrepJob && <ReportView report={report} />}
      {report && isPrepJob && (
        <section className="rounded-2xl border border-line bg-panel/90 p-6">
          <h2 className="text-xl font-semibold">Подготовка</h2>
          <p className="mt-2 text-sm text-muted">
            Файлы нормализованы. Скачайте их вместе с промптом и отправьте в свой чат.
          </p>
          <pre className="mt-4 overflow-auto rounded-xl bg-white/80 p-4 font-mono text-xs whitespace-pre-wrap">
            {report}
          </pre>
        </section>
      )}
    </div>
  )
}

function ModeCard({
  active,
  title,
  text,
  onClick,
}: {
  active: boolean
  title: string
  text: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded-2xl border px-5 py-4 text-left transition',
        active
          ? 'border-accent bg-accent-soft shadow-sm'
          : 'border-line bg-panel/80 hover:border-accent',
      ].join(' ')}
    >
      <div className="text-base font-semibold">{title}</div>
      <p className="mt-1 text-sm text-muted">{text}</p>
    </button>
  )
}

function StepChip({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded-full px-4 py-2 text-sm font-medium transition',
        active
          ? 'bg-accent text-accent-ink'
          : 'border border-line bg-white text-muted hover:border-accent',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function Dropzone({
  label,
  file,
  onFile,
  accept,
}: {
  label: string
  file: File | null
  onFile: (f: File | null) => void
  accept: 'xyz' | 'json'
}) {
  const [dragOver, setDragOver] = useState(false)
  const ext = accept === 'json' ? /\.json$/i : /\.xyz$/i
  const acceptAttr =
    accept === 'json' ? '.json,application/json,text/plain' : '.xyz,chemical/x-xyz,text/plain'
  const hint =
    accept === 'json'
      ? 'Перетащите .json сюда или нажмите, чтобы выбрать'
      : 'Перетащите .xyz сюда или нажмите, чтобы выбрать'

  return (
    <label
      className={[
        'flex min-h-36 cursor-pointer flex-col items-start justify-center gap-2 rounded-xl border border-dashed px-4 py-6 text-left transition',
        dragOver ? 'border-accent bg-accent-soft' : 'border-line bg-white/80 hover:border-accent',
      ].join(' ')}
      onDragEnter={(e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragOver(true)
      }}
      onDragOver={(e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragOver(true)
      }}
      onDragLeave={(e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragOver(false)
        onFile(pickFile(e.dataTransfer.files, ext))
      }}
    >
      <span className="text-sm font-semibold">{label}</span>
      <span className="text-sm text-muted">{file ? file.name : hint}</span>
      <input
        className="hidden"
        type="file"
        accept={acceptAttr}
        onChange={(e) => onFile(pickFile(e.target.files, ext))}
      />
    </label>
  )
}
