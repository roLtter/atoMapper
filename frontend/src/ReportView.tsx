import { useMemo, useState } from 'react'

type Section = {
  key: string
  title: string
  lines: string[]
}

type Summary = {
  mapping: string | null
  rmsd: string | null
  broken: string | null
  formed: string | null
  method: string | null
  accepted: string | null
  formula: string | null
  nAtoms: string | null
}

function parseSections(md: string): Section[] {
  const lines = md.split(/\r?\n/)
  const sections: Section[] = []
  let current: Section | null = null
  for (const raw of lines) {
    const line = raw.trimEnd()
    const h2 = /^##\s+(.+)/.exec(line)
    if (h2) {
      current = { key: h2[1].toLowerCase(), title: h2[1], lines: [] }
      sections.push(current)
      continue
    }
    if (!current) continue
    if (line.startsWith('# ')) continue
    if (line.trim() === '') continue
    current.lines.push(line.replace(/^\s*-\s*/, ''))
  }
  return sections
}

function extractSummary(sections: Section[]): Summary {
  const all = sections.flatMap((s) => s.lines)
  const find = (re: RegExp) => {
    for (const line of all) {
      const m = re.exec(line)
      if (m) return m[1] ?? m[0]
    }
    return null
  }
  return {
    mapping: find(/chosen mapping:\s*(.+)/i),
    rmsd: find(/rmsd=([0-9.]+)/i),
    broken: find(/broken=(\[[^\]]*\])/i),
    formed: find(/formed=(\[[^\]]*\])/i),
    method: find(/method:\s*(.+)/i),
    accepted: find(/verifier:\s*(.+)/i),
    formula: find(/formula:\s*(\{.+?\})/i),
    nAtoms: find(/reactant atoms:\s*(\d+)/i),
  }
}

const SECTION_HINT: Record<string, string> = {
  parse: 'Состав и число атомов. Формулы reactant/product должны совпасть.',
  bonds: 'Сколько связей нашли по геометрии до маппинга.',
  normalize: 'Как подготовили позы для модели (на выход NEB это не влияет).',
  selection: 'Как выбрали mapping: LLM, проверки, fallback, метрики.',
}

function SectionCard({ section }: { section: Section }) {
  const hint = SECTION_HINT[section.key]
  return (
    <article className="rounded-xl border border-[var(--line)] bg-white/80 p-4">
      <h3 className="text-sm font-semibold tracking-wide text-[var(--accent)] uppercase">{section.title}</h3>
      {hint && <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p>}
      <ul className="mt-3 space-y-1.5 text-sm leading-relaxed text-[var(--ink)]">
        {section.lines.map((line, i) => (
          <li key={`${section.key}-${i}`} className="font-mono text-[13px] break-all">
            {line}
          </li>
        ))}
      </ul>
    </article>
  )
}

export function ReportView({ report }: { report: string }) {
  const [copied, setCopied] = useState(false)
  const sections = useMemo(() => parseSections(report), [report])
  const summary = useMemo(() => extractSummary(sections), [sections])

  async function copyRaw() {
    await navigator.clipboard.writeText(report)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <section className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Отчёт маппинга</h2>
          <p className="text-sm text-[var(--muted)]">Кратко для проверки, ниже разбор по шагам</p>
        </div>
        <button
          type="button"
          onClick={copyRaw}
          className="rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-sm font-medium hover:bg-[var(--accent-soft)]"
        >
          {copied ? 'Скопировано' : 'Copy raw report'}
        </button>
      </div>

      <div className="grid gap-3 rounded-xl border border-[var(--accent)]/25 bg-[var(--accent-soft)]/60 p-4 sm:grid-cols-2">
        <SummaryItem label="Атомы" value={summary.nAtoms ? `${summary.nAtoms}` : '—'} />
        <SummaryItem label="Формула" value={summary.formula ?? '—'} mono />
        <SummaryItem label="RMSD" value={summary.rmsd ?? '—'} mono emphasize />
        <SummaryItem label="Источник" value={summary.accepted ?? summary.method ?? '—'} />
        <SummaryItem
          label="Mapping"
          value={summary.mapping ?? '—'}
          mono
          className="sm:col-span-2"
        />
        <SummaryItem label="Broken bonds" value={summary.broken ?? '[]'} mono className="sm:col-span-1" warn />
        <SummaryItem label="Formed bonds" value={summary.formed ?? '[]'} mono className="sm:col-span-1" warn />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {sections.map((s) => (
          <SectionCard key={s.key} section={s} />
        ))}
      </div>
    </section>
  )
}

function SummaryItem({
  label,
  value,
  mono,
  emphasize,
  warn,
  className = '',
}: {
  label: string
  value: string
  mono?: boolean
  emphasize?: boolean
  warn?: boolean
  className?: string
}) {
  return (
    <div className={className}>
      <p className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">{label}</p>
      <p
        className={[
          'mt-1 text-sm break-all',
          mono ? 'font-mono' : 'font-medium',
          emphasize ? 'text-lg text-[var(--ok)]' : '',
          warn ? 'text-[var(--warn)]' : 'text-[var(--ink)]',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {value}
      </p>
    </div>
  )
}
