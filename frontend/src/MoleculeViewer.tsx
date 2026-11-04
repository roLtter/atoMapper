import { useEffect, useRef } from 'react'

type Props = {
  title: string
  xyz: string
}

export function MoleculeViewer({ title, xyz }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || !xyz) return
    let cancelled = false

    ;(async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod: any = await import('3dmol/build/3Dmol.js')
      const $3Dmol = mod.default ?? mod
      if (cancelled || !ref.current) return
      ref.current.innerHTML = ''
      const viewer = $3Dmol.createViewer(ref.current, { backgroundColor: '#fffcf7' })
      viewer.addModel(xyz, 'xyz')
      viewer.setStyle({}, { stick: { radius: 0.12 }, sphere: { scale: 0.22 } })
      viewer.zoomTo()
      viewer.render()
    })()

    return () => {
      cancelled = true
      if (ref.current) ref.current.innerHTML = ''
    }
  }, [xyz])

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{title}</p>
      <div ref={ref} className="h-64 w-full overflow-hidden rounded-xl border border-[var(--line)] bg-white" />
    </div>
  )
}
