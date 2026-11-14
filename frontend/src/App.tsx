import { useEffect, useMemo, useState } from 'react'
import { MoleculeViewer } from './MoleculeViewer'
import { ReportView } from './ReportView'

type Job = {
  job_id: string
  status: string
  step: string
  error?: string
}

const FILES = [
  'reactant_mapped.xyz',
  'product_mapped.xyz',
  'mapping.json',
  'report.md',
] as const

export default function App() {
  const [reactant, setReactant] = useState<File | null>(null)
  const [product, setProduct] = useState<File | null>(null)
  const [charge, setCharge] = useState(0)
  const [multiplicity, setMultiplicity] = useState(1)
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [report, setReport] = useState('')
  const [reactantXyz, setReactantXyz] = useState('')
  const [productXyz, setProductXyz] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const canSubmit = useMemo(() => !!reactant && !!product && !busy, [reactant, product, busy])
  const done = job?.status === 'done' && !!jobId

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
          const [reportRes, rXyz, pXyz] = await Promise.all([
            fetch(`/api/jobs/${jobId}/files/report.md`),
            fetch(`/api/jobs/${jobId}/files/reactant_mapped.xyz`),
            fetch(`/api/jobs/${jobId}/files/product_mapped.xyz`),
          ])
          if (reportRes.ok) setReport(await reportRes.text())
          if (rXyz.ok) setReactantXyz(await rXyz.text())
          if (pXyz.ok) setProductXyz(await pXyz.text())
          setBusy(false)
          return
        }
        if (data.status === 'failed') {
          setError(data.error || 'job failed')
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
  }, [jobId])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reactant || !product) return
    setBusy(true)
    setError('')
    setReport('')
    setReactantXyz('')
    setProductXyz('')
    setJob(null)
    setJobId(null)
    const body = new FormData()
    body.append('reactant', reactant)
    body.append('product', product)
    body.append('charge', String(charge))
    body.append('multiplicity', String(multiplicity))
    body.append('use_llm', 'true')
    try {
      const res = await fetch('/api/jobs', { method: 'POST', body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || res.statusText)
      setJobId(data.job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  async function downloadMapped() {
    if (!jobId) return
    for (const name of ['reactant_mapped.xyz', 'product_mapped.xyz'] as const) {
      const res = await fetch(`/api/jobs/${jobId}/files/${name}`)
      if (!res.ok) continue
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.click()
      URL.revokeObjectURL(url)
      await new Promise((r) => setTimeout(r, 150))
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-4 py-10">
      <header className="space-y-3">
        <h1
          className="text-4xl tracking-tight text-[var(--ink)] md:text-5xl"
          style={{ fontFamily: 'var(--serif)' }}
        >
          atoMapper
        </h1>
        <p className="max-w-2xl text-[var(--muted)]">
          Согласуй нумерацию атомов в reactant/product `.xyz` для ORCA NEB и получи отчёт по связям.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="grid gap-6 rounded-2xl border border-[var(--line)] bg-[var(--panel)]/90 p-6 shadow-sm md:grid-cols-2"
      >
        <Dropzone label="Reactant" file={reactant} onFile={setReactant} />
        <Dropzone label="Product" file={product} onFile={setProduct} />

        <label className="flex flex-col gap-1 text-sm">
          Charge
          <input
            className="rounded-lg border border-[var(--line)] bg-white px-3 py-2"
            type="number"
            value={charge}
            onChange={(e) => setCharge(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Multiplicity
          <input
            className="rounded-lg border border-[var(--line)] bg-white px-3 py-2"
            type="number"
            min={1}
            value={multiplicity}
            onChange={(e) => setMultiplicity(Number(e.target.value))}
          />
        </label>

        <button
          type="submit"
          disabled={!canSubmit}
          className="md:col-span-2 rounded-xl bg-[var(--accent)] px-4 py-3 font-semibold text-[var(--accent-ink)] disabled:opacity-40"
        >
          {busy ? 'Running…' : 'Map atoms'}
        </button>
      </form>

      {(job || error) && (
        <section className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--panel)]/90 p-6">
          <h2 className="text-xl font-semibold">Status</h2>
          {job && (
            <p className="font-mono text-sm text-[var(--muted)]">
              {job.job_id} · {job.status} · {job.step}
            </p>
          )}
          {error && <p className="text-sm text-red-700">{error}</p>}
          {done && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={downloadMapped}
                className="rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-semibold text-[var(--accent-ink)]"
              >
                Скачать готовые файлы
              </button>
              {FILES.filter((n) => n === 'mapping.json' || n === 'report.md').map((name) => (
                <a
                  key={name}
                  className="rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-sm hover:bg-[var(--accent-soft)]"
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

      {done && (reactantXyz || productXyz) && (
        <section className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--panel)]/90 p-6">
          <h2 className="text-xl font-semibold">Mapped structures</h2>
          <div className="grid min-w-0 gap-6 md:grid-cols-2">
            {reactantXyz ? (
              <MoleculeViewer title="reactant_mapped.xyz" xyz={reactantXyz} />
            ) : (
              <p className="text-sm text-[var(--muted)]">reactant_mapped.xyz недоступен</p>
            )}
            {productXyz ? (
              <MoleculeViewer title="product_mapped.xyz" xyz={productXyz} />
            ) : (
              <p className="text-sm text-[var(--muted)]">product_mapped.xyz недоступен</p>
            )}
          </div>
        </section>
      )}

      {report && <ReportView report={report} />}
    </div>
  )
}

function Dropzone({
  label,
  file,
  onFile,
}: {
  label: string
  file: File | null
  onFile: (f: File | null) => void
}) {
  return (
    <label className="flex min-h-36 cursor-pointer flex-col items-start justify-center gap-2 rounded-xl border border-dashed border-[var(--line)] bg-white/80 px-4 py-6 text-left transition hover:border-[var(--accent)]">
      <span className="text-sm font-semibold">{label}</span>
      <span className="text-sm text-[var(--muted)]">{file ? file.name : 'Drop .xyz or click'}</span>
      <input
        className="hidden"
        type="file"
        accept=".xyz,chemical/x-xyz,text/plain"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </label>
  )
}
