import { useEffect, useId, useRef, useState } from 'react'

type Props = {
  title: string
  xyz: string
}

type AtomInfo = {
  index: number
  elem: string
}

type ViewerApi = {
  addModel: (d: string, f: string) => void
  setStyle: (sel: object, style: object) => void
  setClickable: (
    sel: object,
    clickable: boolean,
    cb: (atom: { index?: number; serial?: number; elem?: string }) => void,
  ) => void
  zoomTo: () => void
  zoom: (f: number) => void
  render: () => void
  resize: () => void
  clear?: () => void
  getCanvas?: () => HTMLCanvasElement | null
}

const DEFAULT_STYLE = { stick: { radius: 0.14 }, sphere: { scale: 0.25 } }

function parseAtoms(xyz: string): AtomInfo[] {
  const lines = xyz.split(/\r?\n/)
  const n = parseInt(lines[0]?.trim() ?? '0', 10)
  const atoms: AtomInfo[] = []
  for (let i = 0; i < n; i++) {
    const parts = (lines[i + 2] ?? '').trim().split(/\s+/)
    if (!parts[0]) continue
    atoms.push({ elem: parts[0], index: i + 1 })
  }
  return atoms
}

export function MoleculeViewer({ title, xyz }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<ViewerApi | null>(null)
  const viewerId = useId().replace(/:/g, '')
  const [selected, setSelected] = useState<AtomInfo | null>(null)

  useEffect(() => {
    if (!hostRef.current || !xyz) return
    let cancelled = false
    let viewer: ViewerApi | null = null
    let canvas: HTMLCanvasElement | null = null
    let onWheel: ((ev: WheelEvent) => void) | null = null
    const atomMeta = parseAtoms(xyz)

    setSelected(null)

    ;(async () => {
      const mod = (await import('3dmol/build/3Dmol.js')) as {
        default?: { createViewer: (el: HTMLElement, opts: object) => ViewerApi }
        createViewer?: (el: HTMLElement, opts: object) => ViewerApi
      }
      const $3Dmol = mod.default ?? mod
      if (cancelled || !hostRef.current || !$3Dmol.createViewer) return

      hostRef.current.innerHTML = ''
      const el = hostRef.current
      el.style.width = '100%'
      el.style.height = '100%'
      el.style.position = 'relative'

      viewer = $3Dmol.createViewer(el, {
        backgroundColor: '#f8fafc',
        id: viewerId,
      })
      viewerRef.current = viewer
      viewer.addModel(xyz, 'xyz')
      viewer.setStyle({}, DEFAULT_STYLE)
      viewer.setClickable({}, true, (atom) => {
        const i = typeof atom.index === 'number' ? atom.index : (atom.serial ?? 1) - 1
        const meta = atomMeta[i] ?? {
          index: i + 1,
          elem: atom.elem ?? '?',
        }
        setSelected(meta)
        viewer?.setStyle({}, DEFAULT_STYLE)
        viewer?.setStyle(
          { index: i },
          { stick: { radius: 0.16 }, sphere: { scale: 0.35 }, color: '#0284c7' },
        )
        viewer?.render()
      })
      viewer.zoomTo()
      viewer.render()

      canvas = viewer.getCanvas?.() ?? el.querySelector('canvas')
      if (canvas) {
        onWheel = (ev: WheelEvent) => {
          ev.preventDefault()
          ev.stopImmediatePropagation()
          if (!viewer) return
          const factor = ev.deltaY < 0 ? 1.12 : 0.89
          viewer.zoom(factor)
          viewer.render()
        }
        canvas.addEventListener('wheel', onWheel, { capture: true, passive: false })
      }

      requestAnimationFrame(() => {
        if (cancelled || !viewer) return
        viewer.resize()
        viewer.zoomTo()
        viewer.render()
      })
    })()

    return () => {
      cancelled = true
      viewerRef.current = null
      if (canvas && onWheel) canvas.removeEventListener('wheel', onWheel, true)
      try {
        viewer?.clear?.()
      } catch {
        void 0
      }
      if (hostRef.current) hostRef.current.innerHTML = ''
    }
  }, [xyz, viewerId])

  function resetView() {
    const viewer = viewerRef.current
    if (!viewer) return
    setSelected(null)
    viewer.setStyle({}, DEFAULT_STYLE)
    viewer.zoomTo()
    viewer.render()
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{title}</p>
        <button
          type="button"
          onClick={resetView}
          className="rounded-md border border-[var(--line)] bg-white px-2 py-0.5 text-xs font-medium text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          reset
        </button>
      </div>
      <div className="relative h-72 w-full overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div ref={hostRef} className="absolute inset-0" />
      </div>
      <p className="min-h-5 text-sm text-[var(--muted)]">
        {selected ? (
          <>
            Атом <span className="font-medium text-[var(--ink)]">{selected.elem}</span> · номер в файле{' '}
            <span className="font-medium text-[var(--ink)]">{selected.index}</span>
          </>
        ) : (
          'Кликните по атому, чтобы увидеть элемент и номер'
        )}
      </p>
    </div>
  )
}
