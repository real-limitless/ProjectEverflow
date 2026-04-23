import React, { useState } from 'react';
import { Card, CardBody, Button, ExpandableSection } from '@patternfly/react-core';
import { executeProjectTool } from '@/lib/api';
import { ProjectTool } from '@/lib/api';
import { CopyIcon } from '@patternfly/react-icons';

interface ToolCall {
  id?: string;
  name: string;
  args?: Record<string, any>;
  output?: string;
}

interface ToolOutputProps {
  toolCall: ToolCall;
  projectId: number;
  projectTools?: ProjectTool[];
}

export const ToolOutput: React.FC<ToolOutputProps> = ({ toolCall, projectId, projectTools = [] }) => {
  const [expanded, setExpanded] = useState(true);
  const [output, setOutput] = useState<string | undefined>(toolCall.output as any);
  const [running, setRunning] = useState(false);

  const findTool = () => projectTools.find(t => t.name === toolCall.name || t.slug === toolCall.name || `${t.name}`.toLowerCase() === toolCall.name.toLowerCase());

  const handleRerun = async () => {
    const tool = findTool();
    if (!tool) {
      setOutput('No matching project tool found to rerun.');
      return;
    }
    setRunning(true);
    try {
      const resp = await executeProjectTool(tool.id, toolCall.args || {});
      if (resp.data && resp.data.output) {
        setOutput(JSON.stringify(resp.data.output, null, 2));
      } else {
        setOutput('No output returned from tool execution.');
      }
    } catch (e: any) {
      setOutput(`Error running tool: ${e?.message || String(e)}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card className="mt-2">
      <CardBody>
        <div className="flex items-start gap-4">
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">{toolCall.name}</div>
              <div className="flex gap-2">
                <Button variant="plain" onClick={() => navigator.clipboard?.writeText(JSON.stringify(toolCall.args || {}))} aria-label="Copy args"><CopyIcon /></Button>
                <Button variant="secondary" onClick={() => setExpanded(prev => !prev)}>{expanded ? 'Hide' : 'Show'}</Button>
                <Button isDisabled={running} variant="primary" onClick={handleRerun}>{running ? 'Running...' : 'Rerun'}</Button>
              </div>
            </div>
            <div className="text-xs text-muted-foreground mt-2">Args: <code className="break-all">{JSON.stringify(toolCall.args || {})}</code></div>
            <ExpandableSection isExpanded={expanded} toggleText={expanded ? 'Hide output' : 'Show output'}>
              <pre className="mt-2 whitespace-pre-wrap bg-surface rounded-md p-2 text-sm">{output ?? 'No output yet'}</pre>
            </ExpandableSection>
          </div>
        </div>
      </CardBody>
    </Card>
  );
};

export default ToolOutput;
