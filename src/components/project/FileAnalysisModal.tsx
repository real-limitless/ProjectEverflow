import { useState, useEffect } from 'react';
import { Modal, ModalVariant, Button, Spinner, Progress, Card, CardBody, Alert, AlertVariant } from '@patternfly/react-core';
import { AlertTriangle, CheckCircle2, Loader2, BarChart3 } from 'lucide-react';
import { streamFileAnalysis, AnalyzeStreamEvent } from '@/lib/api';
import { toast } from '@/hooks/use-toast';

interface FileAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: number;
  filePath: string;
}

interface AnalysisResult {
  summary?: any;
  chunks?: any[];
  totalChunks?: number;
  totalLines?: number;
  totalTodos?: number;
  totalFunctions?: number;
}

export const FileAnalysisModal: React.FC<FileAnalysisModalProps> = ({
  isOpen,
  onClose,
  projectId,
  filePath,
}) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'quick' | 'deep'>('quick');

  const handleStartAnalysis = async () => {
    setIsAnalyzing(true);
    setProgress(0);
    setError(null);
    setAnalysisResult(null);

    try {
      await streamFileAnalysis(
        projectId,
        filePath,
        mode,
        (event: AnalyzeStreamEvent) => {
          if (event.type === 'analyze_start') {
            setProgress(1);
          } else if (event.type === 'analyze_progress') {
            setProgress(event.progress || 0);
            if (event.chunk) {
              setAnalysisResult(prev => ({
                ...prev,
                chunks: [...(prev?.chunks || []), event.chunk],
              }));
            }
          } else if (event.type === 'analyze_complete') {
            setProgress(100);
            if (event.summary) {
              setAnalysisResult(prev => ({
                ...prev,
                summary: event.summary,
                totalChunks: event.summary.total_chunks,
                totalLines: event.summary.total_lines,
                totalTodos: event.summary.total_todos,
                totalFunctions: event.summary.total_functions,
              }));
            }
          } else if (event.type === 'analyze_error') {
            setError(event.message || 'Unknown error occurred');
          }
        },
        (error) => {
          setError(error.message || 'Analysis failed');
          setIsAnalyzing(false);
        },
        () => {
          setIsAnalyzing(false);
        }
      );
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Analysis failed';
      setError(errorMsg);
      setIsAnalyzing(false);
    }
  };

  const handleClose = () => {
    if (!isAnalyzing) {
      setProgress(0);
      setAnalysisResult(null);
      setError(null);
      setMode('quick');
      onClose();
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="File Analysis"
      variant={ModalVariant.medium}
      size="lg"
    >
      <div className="space-y-4">
        {!isAnalyzing && !analysisResult && !error ? (
          <>
            <p className="text-sm text-muted-foreground">
              Analyze <code className="bg-gray-100 px-2 py-1 rounded">{filePath}</code> for potential issues, TODOs, and metrics.
            </p>

            <div className="space-y-3">
              <label className="block">
                <span className="text-sm font-medium text-foreground mb-2 block">Analysis Mode</span>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      value="quick"
                      checked={mode === 'quick'}
                      onChange={(e) => setMode(e.target.value as 'quick' | 'deep')}
                      className="w-4 h-4"
                    />
                    <span className="text-sm">
                      <strong>Quick</strong> - Fast overview (file stats, TODOs)
                    </span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      value="deep"
                      checked={mode === 'deep'}
                      onChange={(e) => setMode(e.target.value as 'quick' | 'deep')}
                      className="w-4 h-4"
                    />
                    <span className="text-sm">
                      <strong>Deep</strong> - Detailed analysis with chunk breakdown (slower)
                    </span>
                  </label>
                </div>
              </label>
            </div>

            <div className="flex gap-2 justify-end pt-4">
              <Button variant="secondary" onClick={handleClose}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleStartAnalysis}>
                Start Analysis
              </Button>
            </div>
          </>
        ) : error ? (
          <>
            <Alert variant={AlertVariant.danger} title="Analysis Failed">
              <p className="text-sm">{error}</p>
            </Alert>
            <div className="flex gap-2 justify-end pt-4">
              <Button variant="secondary" onClick={handleClose}>
                Close
              </Button>
              <Button variant="primary" onClick={handleStartAnalysis}>
                Try Again
              </Button>
            </div>
          </>
        ) : isAnalyzing ? (
          <>
            <div className="space-y-3">
              <p className="text-sm font-medium">Analyzing file...</p>
              <Progress value={progress} title={`${progress}%`} />
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {mode === 'deep' && analysisResult?.chunks && (
                  <span>Chunk {analysisResult.chunks.length} of {analysisResult.totalChunks || '?'}</span>
                )}
                {mode === 'quick' && <span>Gathering file statistics...</span>}
              </div>
            </div>
            <div className="flex gap-2 justify-end pt-4">
              <Button variant="secondary" onClick={handleClose} isDisabled={true}>
                Close
              </Button>
            </div>
          </>
        ) : analysisResult ? (
          <>
            <div className="space-y-4">
              {mode === 'quick' && analysisResult.summary ? (
                <Card>
                  <CardBody>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Lines</p>
                        <p className="text-2xl font-bold">{analysisResult.summary.lines}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Characters</p>
                        <p className="text-2xl font-bold">{analysisResult.summary.chars}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Language</p>
                        <p className="text-2xl font-bold">{analysisResult.summary.lang}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">TODOs/FIXMEs</p>
                        <p className={`text-2xl font-bold ${analysisResult.summary.todos.length > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                          {analysisResult.summary.todos.length}
                        </p>
                      </div>
                    </div>
                    {analysisResult.summary.todos.length > 0 && (
                      <div className="mt-4 pt-4 border-t">
                        <p className="text-sm font-medium mb-2">TODOs/FIXMEs Found:</p>
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                          {analysisResult.summary.todos.slice(0, 10).map((todo: any, idx: number) => (
                            <div key={idx} className="text-xs text-muted-foreground">
                              <strong>Line {todo.line}:</strong> {todo.text.substring(0, 60)}
                            </div>
                          ))}
                          {analysisResult.summary.todos.length > 10 && (
                            <div className="text-xs text-muted-foreground font-semibold">
                              +{analysisResult.summary.todos.length - 10} more...
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </CardBody>
                </Card>
              ) : mode === 'deep' && analysisResult.summary ? (
                <Card>
                  <CardBody>
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 mb-4">
                        <BarChart3 className="h-5 w-5 text-blue-500" />
                        <h3 className="font-semibold">Analysis Summary</h3>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="border rounded p-3">
                          <p className="text-sm text-muted-foreground">Total Lines</p>
                          <p className="text-2xl font-bold">{analysisResult.totalLines}</p>
                        </div>
                        <div className="border rounded p-3">
                          <p className="text-sm text-muted-foreground">Total Chunks</p>
                          <p className="text-2xl font-bold">{analysisResult.totalChunks}</p>
                        </div>
                        <div className="border rounded p-3">
                          <p className="text-sm text-muted-foreground">Functions</p>
                          <p className="text-2xl font-bold">{analysisResult.totalFunctions}</p>
                        </div>
                        <div className="border rounded p-3">
                          <p className="text-sm text-muted-foreground">TODOs/FIXMEs</p>
                          <p className={`text-2xl font-bold ${(analysisResult.totalTodos || 0) > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
                            {analysisResult.totalTodos || 0}
                          </p>
                        </div>
                      </div>

                      {analysisResult.chunks && analysisResult.chunks.length > 0 && (
                        <div className="mt-4 pt-4 border-t">
                          <p className="text-sm font-medium mb-3">Chunk Breakdown:</p>
                          <div className="space-y-2 max-h-64 overflow-y-auto">
                            {analysisResult.chunks.map((chunk, idx) => (
                              <div key={idx} className="border rounded p-2 text-xs">
                                <div className="flex justify-between mb-1">
                                  <strong>Chunk {chunk.chunk_index}/{chunk.total_chunks}</strong>
                                  <span className="text-muted-foreground">{chunk.lines} lines</span>
                                </div>
                                <div className="grid grid-cols-3 gap-2 text-muted-foreground">
                                  <span>Functions: {chunk.functions}</span>
                                  <span>TODOs: {chunk.todos}</span>
                                  <span>Long lines: {chunk.long_lines}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </CardBody>
                </Card>
              ) : null}

              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle2 className="h-5 w-5" />
                <span className="text-sm font-medium">Analysis complete</span>
              </div>
            </div>

            <div className="flex gap-2 justify-end pt-4">
              <Button variant="secondary" onClick={handleClose}>
                Close
              </Button>
              <Button variant="primary" onClick={handleStartAnalysis}>
                Re-analyze
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  );
};
