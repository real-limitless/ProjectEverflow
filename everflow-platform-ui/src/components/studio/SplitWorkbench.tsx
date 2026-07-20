import type { ReactNode } from 'react'

interface SplitWorkbenchProps {
  sidebar: ReactNode
  main: ReactNode
  results?: ReactNode
  sidebarWidth?: number | string
  resultsHeight?: number | string
  className?: string
}

/** Left sidebar + main editor + optional bottom results pane. */
export function SplitWorkbench({
  sidebar,
  main,
  results,
  sidebarWidth = 220,
  resultsHeight = '38%',
  className = '',
}: SplitWorkbenchProps) {
  return (
    <div className={`studio-split-workbench ${className}`.trim()}>
      <aside className="studio-split-sidebar" style={{ width: sidebarWidth, minWidth: sidebarWidth }}>
        {sidebar}
      </aside>
      <div className="studio-split-center">
        <div className="studio-split-main">{main}</div>
        {results != null && (
          <div className="studio-split-results" style={{ flexBasis: resultsHeight, maxHeight: resultsHeight }}>
            {results}
          </div>
        )}
      </div>
    </div>
  )
}
