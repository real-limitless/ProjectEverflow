/** Module-level drag state — avoid React setState in dragStart (cancels HTML5 DnD). */

let activePanelId: string | null = null

export function beginPanelDrag(panelId: string): void {
  activePanelId = panelId
  document.body.classList.add('is-panel-dragging')
}

export function endPanelDrag(): void {
  activePanelId = null
  document.body.classList.remove('is-panel-dragging')
}

export function getDraggingPanelId(): string | null {
  return activePanelId
}
