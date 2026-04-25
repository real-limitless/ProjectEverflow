import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@patternfly/react-core';
import { Card, CardBody } from '@patternfly/react-core';
import { AlertTriangle, CheckCircle, Code, FileText } from 'lucide-react';

interface Chunk {
  chunk_index: number;
  total_chunks?: number;
  summary?: any;
  snippet?: string;
  progress?: number;
}

interface Props {
  isOpen: boolean;
  onOpenChange: (v: boolean) => void;
  chunks: Chunk[];
  final: any | null;
  onCreateChangeRequest?: (summary: string) => Promise<void>;
}

export const AnalysisStreamModal: React.FC<Props> = ({ isOpen, onOpenChange, chunks, final, onCreateChangeRequest }) => {
  const sorted = [...chunks].sort((a, b) => (a.chunk_index || 0) - (b.chunk_index || 0));

  const total = final?.total_chunks ?? (sorted.length || undefined);
  const todos = final?.total_todos ?? 0;
  const functions = final?.total_functions ?? 0;
  const lines = final?.total_lines ?? 0;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Code Analysis Report</DialogTitle>
        </DialogHeader>

        <div className="p-4 space-y-4">
          {/* Progress Bar */}
          <div className="p-3 border rounded bg-gradient-to-r from-blue-50 to-blue-100 dark:from-slate-800 dark:to-slate-900">
            <div className="text-sm font-semibold text-foreground mb-2">Analysis Progress</div>
            <div className="w-full bg-slate-200 dark:bg-slate-700 rounded h-2">
              <div 
                className="bg-blue-500 h-2 rounded transition-all" 
                style={{ width: total ? `${Math.min(100, (sorted.length / total) * 100)}%` : '0%' }}
              />
            </div>
            <div className="text-xs text-muted-foreground mt-2">{sorted.length} / {total ?? '...'} chunks analyzed</div>
          </div>

          {/* Summary Metrics */}
          {final && (
            <div className="grid grid-cols-4 gap-3">
              <Card className="p-0">
                <CardBody className="p-3">
                  <div className="text-xs text-muted-foreground">Lines of Code</div>
                  <div className="text-2xl font-bold">{lines.toLocaleString()}</div>
                </CardBody>
              </Card>
              <Card className="p-0">
                <CardBody className="p-3">
                  <div className="text-xs text-muted-foreground">Functions/Classes</div>
                  <div className="text-2xl font-bold text-blue-600">{functions}</div>
                </CardBody>
              </Card>
              <Card className="p-0">
                <CardBody className="p-3">
                  <div className="text-xs text-muted-foreground">TODOs/FIXMEs</div>
                  <div className="text-2xl font-bold text-orange-600">{todos}</div>
                </CardBody>
              </Card>
              <Card className="p-0">
                <CardBody className="p-3">
                  <div className="text-xs text-muted-foreground">Complexity</div>
                  <div className="text-2xl font-bold text-green-600">
                    {Math.round(functions > 0 ? lines / functions : lines)}
                  </div>
                </CardBody>
              </Card>
            </div>
          )}

          {/* Chunk Details */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">Analyzed Chunks</div>
            {sorted.map((c) => {
              const summary = c.summary || {};
              const chunkTodos = summary.todos || 0;
              const chunkFunctions = summary.functions || 0;
              const chunkLines = summary.lines || 0;

              return (
                <Card key={c.chunk_index} className="p-0">
                  <CardBody className="p-3">
                    <div className="flex justify-between items-start mb-2">
                      <div className="text-sm font-medium">Chunk {c.chunk_index} of {c.total_chunks ?? total ?? '?'}</div>
                      <div className="text-xs text-muted-foreground">
                        {Math.round(((c.chunk_index || 0) / (total || 1)) * 100)}% complete
                      </div>
                    </div>

                    {/* Metrics Grid */}
                    <div className="grid grid-cols-3 gap-2 text-xs mb-2 p-2 bg-muted rounded">
                      <div>
                        <FileText className="inline w-3 h-3 mr-1" />
                        <span className="font-medium">{chunkLines} lines</span>
                      </div>
                      <div>
                        <Code className="inline w-3 h-3 mr-1" />
                        <span className="font-medium">{chunkFunctions} functions</span>
                      </div>
                      <div>
                        {chunkTodos > 0 ? (
                          <>
                            <AlertTriangle className="inline w-3 h-3 mr-1 text-orange-500" />
                            <span className="font-medium text-orange-600">{chunkTodos} TODOs</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle className="inline w-3 h-3 mr-1 text-green-500" />
                            <span className="font-medium text-green-600">0 TODOs</span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Code Snippet */}
                    {c.snippet && (
                      <div className="mt-2">
                        <div className="text-xs font-semibold text-muted-foreground mb-1">Code Preview</div>
                        <pre className="text-xs bg-slate-900 text-slate-100 p-2 rounded overflow-x-auto max-h-32">
                          {c.snippet.slice(0, 300)}
                          {c.snippet.length > 300 ? '\n...[truncated]' : ''}
                        </pre>
                      </div>
                    )}
                  </CardBody>
                </Card>
              );
            })}
          </div>

          {/* Final Summary */}
          {final && (
            <Card className="p-0 border-2 border-blue-200 dark:border-blue-800">
              <CardBody className="p-4 bg-blue-50 dark:bg-blue-950">
                <div className="text-lg font-bold mb-3">📊 Analysis Summary</div>
                <div className="space-y-2 text-sm">
                  <div><span className="font-semibold">Total Lines:</span> {final.total_lines || 0} LOC</div>
                  <div><span className="font-semibold">Total Functions:</span> {final.total_functions || 0}</div>
                  <div><span className="font-semibold">Total TODOs/FIXMEs:</span> <span className="text-orange-600 font-bold">{final.total_todos || 0}</span></div>
                  <div><span className="font-semibold">Total Chunks:</span> {final.total_chunks || 0}</div>
                  <div className="mt-3 p-2 bg-white dark:bg-slate-800 rounded text-xs">
                    <span className="font-semibold">Key Insight:</span> This file contains {final.total_functions || 0} logical units across {final.total_lines || 0} lines with {final.total_todos || 0} outstanding items to address.
                  </div>
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default AnalysisStreamModal;