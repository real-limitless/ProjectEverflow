/**
 * Default placement for the floating panel tray: bottom-center of the
 * playground main area so panel type buttons stay fully on-screen.
 */
export function getPlaygroundFloatPalettePos(
  size: { width?: number; height?: number } = {},
): { x: number; y: number } {
  const margin = 16
  const width = size.width ?? 440
  const height = size.height ?? 180

  if (typeof window === 'undefined') {
    return { x: 24, y: 400 }
  }

  const main =
    (document.querySelector('#main-content-playground') as HTMLElement | null) ||
    (document.querySelector('.pg-main-workbench') as HTMLElement | null) ||
    (document.querySelector('.pf-v6-c-page__main') as HTMLElement | null)

  let left = 0
  let right = window.innerWidth
  let bottom = window.innerHeight

  if (main) {
    const r = main.getBoundingClientRect()
    left = r.left
    right = r.right
    bottom = Math.min(window.innerHeight, r.bottom)
  } else {
    const sidebar = document.getElementById('sidebar')
    if (sidebar) left = sidebar.getBoundingClientRect().right
  }

  const areaWidth = Math.max(0, right - left)
  let x = left + (areaWidth - width) / 2
  let y = bottom - height - margin

  // Keep fully inside the viewport
  x = Math.min(
    Math.max(margin, x),
    Math.max(margin, window.innerWidth - width - margin),
  )
  y = Math.min(
    Math.max(margin, y),
    Math.max(margin, window.innerHeight - height - margin),
  )

  return { x, y }
}

/** Small recovery chip at bottom-center of the playground (not under the sidebar). */
export function getPlaygroundChipPos(): { x: number; y: number } {
  const chipW = 96
  const chipH = 40
  return getPlaygroundFloatPalettePos({ width: chipW, height: chipH })
}
