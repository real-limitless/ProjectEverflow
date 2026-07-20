/** Module-level drag state — avoid React setState in dragStart (cancels HTML5 DnD). */

let activePanelId: string | null = null

export function beginPanelDrag(panelId: string): void {
  activePanelId = panelId
  // body class added on next frame from DockGroup so the drag gesture locks first
}

export function markPanelDraggingUi(): void {
  if (activePanelId) {
    document.body.classList.add('is-panel-dragging')
  }
}

export function endPanelDrag(): void {
  activePanelId = null
  document.body.classList.remove('is-panel-dragging')
  document
    .querySelectorAll('.drop-zone.hot')
    .forEach((el) => el.classList.remove('hot'))
}

export function getDraggingPanelId(): string | null {
  return activePanelId
}
