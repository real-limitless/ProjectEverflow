import type { PanelKey } from '@/types/panels'
import { typeOf } from '@/lib/panelIds'
import { AgentsPanel } from '@/components/panels/AgentsPanel'
import { ChatPanel } from '@/components/panels/ChatPanel'
import { CodePanel } from '@/components/panels/CodePanel'
import { DatabasePanel } from '@/components/panels/DatabasePanel'
import { DeployPanel } from '@/components/panels/DeployPanel'
import { DesktopPanel } from '@/components/panels/DesktopPanel'
import { EnvPanel } from '@/components/panels/EnvPanel'
import { JobsPanel } from '@/components/panels/JobsPanel'
import { KnowledgePanel } from '@/components/panels/KnowledgePanel'
import { PreviewPanel } from '@/components/panels/PreviewPanel'
import { RepositoryPanel } from '@/components/panels/RepositoryPanel'
import { TerminalPanel } from '@/components/panels/TerminalPanel'
import { TestsPanel } from '@/components/panels/TestsPanel'
import { ToolsPanel } from '@/components/panels/ToolsPanel'
import { WorkflowsPanel } from '@/components/panels/WorkflowsPanel'

interface PanelHostProps {
  panelKey: PanelKey
}

export function PanelHost({ panelKey }: PanelHostProps) {
  const type = typeOf(panelKey)

  return (
    <div
      className="panel-host"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        flex: 1,
        overflow: 'hidden',
      }}
      data-panel-content={panelKey}
    >
      {type === 'chat' && <ChatPanel panelKey={panelKey} />}
      {type === 'preview' && <PreviewPanel />}
      {type === 'desktop' && <DesktopPanel />}
      {type === 'knowledge' && <KnowledgePanel />}
      {type === 'code' && <CodePanel panelKey={panelKey} />}
      {type === 'repository' && <RepositoryPanel />}
      {type === 'terminal' && <TerminalPanel />}
      {type === 'workflows' && <WorkflowsPanel />}
      {type === 'database' && <DatabasePanel />}
      {type === 'jobs' && <JobsPanel />}
      {type === 'agents' && <AgentsPanel />}
      {type === 'tools' && <ToolsPanel />}
      {type === 'env' && <EnvPanel />}
      {type === 'tests' && <TestsPanel />}
      {type === 'deploy' && <DeployPanel />}
      {!type && <div className="empty-group">{panelKey}</div>}
    </div>
  )
}
