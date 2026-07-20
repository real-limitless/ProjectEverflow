import { getProject } from '@/data/projects'
import type { PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'

interface CodePanelProps {
  panelKey: PanelKey
}

export function CodePanel({ panelKey }: CodePanelProps) {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const st = usePlaygroundStore((s) => s.instanceState[panelKey])
  const setCodeFile = usePlaygroundStore((s) => s.setCodeFile)
  const p = getProject(currentProjectId)
  const file = st?.file || p?.files[0]?.name || ''
  const codeHtml = p?.code[file] || ''
  const lines = codeHtml.split('\n')

  const folders = new Map<string, NonNullable<typeof p>['files']>()
  p?.files.forEach((f) => {
    const list = folders.get(f.folder) || []
    list.push(f)
    folders.set(f.folder, list)
  })

  return (
    <div className="code-layout">
      <div className="file-tree">
        <div className="tree-label">Files</div>
        {[...folders.entries()].map(([folder, files]) => (
          <div key={folder}>
            <div className="tree-item folder">{folder}/</div>
            {files.map((f) => (
              <button
                key={f.path}
                type="button"
                className={`tree-item${f.name === file ? ' active' : ''}`}
                onClick={() => setCodeFile(panelKey, f.name)}
              >
                {f.name}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="editor">
        <div className="editor-tabs">
          <div className="editor-tab">{file}</div>
        </div>
        <div className="editor-body">
          <table>
            <tbody>
              {lines.map((line, i) => (
                <tr key={i}>
                  <td className="ln">{i + 1}</td>
                  <td
                    className="code"
                    dangerouslySetInnerHTML={{ __html: line || ' ' }}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
