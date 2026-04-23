import { useState, useEffect, useCallback } from 'react';
import { Button as UIButton } from '@/components/ui/button';
import { Save, RotateCcw } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';

interface CodeEditorProps {
  content?: string;
  fileName?: string;
  isModified: boolean;
  isReadOnly?: boolean;
  onContentChange: (content: string) => void;
  onSave: () => void;
  onDiscard: () => void;
}

/**
 * Detects programming language from file extension
 */
const detectLanguage = (fileName?: string): string => {
  if (!fileName) return 'plaintext';
  // If filename has no extension (Dockerfile, Makefile), use the full lowercased name
  const parts = fileName.split('.');
  const ext = parts.length > 1 ? (parts.pop() || '').toLowerCase() : fileName.toLowerCase();
  const languageMap: Record<string, string> = {
    'ts': 'typescript',
    'tsx': 'typescript',
    'js': 'javascript',
    'jsx': 'javascript',
    'py': 'python',
    'java': 'java',
    'cpp': 'cpp',
    'c': 'c',
    'rs': 'rust',
    'go': 'go',
    'rb': 'ruby',
    'php': 'php',
    'cs': 'csharp',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'clj': 'clojure',
    'ex': 'elixir',
    'erl': 'erlang',
    'pl': 'perl',
    'sh': 'shell',
    'bash': 'shell',
    'zsh': 'shell',
    'fish': 'shell',
    'ps1': 'powershell',
    'r': 'r',
    'lua': 'lua',
    'vim': 'vim',
    'groovy': 'groovy',
    'gradle': 'groovy',
    'xml': 'xml',
    'html': 'html',
    'htm': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',
    'json': 'json',
    'jsonc': 'jsonc',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    'ini': 'ini',
    'cfg': 'ini',
    'conf': 'conf',
    'sql': 'sql',
    'prisma': 'prisma',
    'graphql': 'graphql',
    'md': 'markdown',
    'markdown': 'markdown',
    'tex': 'latex',
    'dockerfile': 'dockerfile',
    'makefile': 'makefile',
    'cmake': 'cmake',
    'git': 'git',
    'diff': 'diff',
    'patch': 'diff',
    'log': 'log',
    'txt': 'plaintext',
    'text': 'plaintext',
  };
  
  return languageMap[ext] || 'plaintext';
};

export const CodeEditor = ({ 
  content, 
  fileName, 
  isModified,
  isReadOnly = false,
  onContentChange, 
  onSave, 
  onDiscard 
}: CodeEditorProps) => {
  const [editorContent, setEditorContent] = useState(content || '');
  const language = detectLanguage(fileName);

  // Update local state when content prop changes (e.g., when file selected)
  useEffect(() => {
    setEditorContent(content || '');
  }, [content, fileName]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newContent = e.target.value;
    setEditorContent(newContent);
    onContentChange(newContent);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+S or Cmd+S to save
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (isModified && !isReadOnly) {
        onSave();
      }
    }
    // Handle Tab key for indentation
    if (e.key === 'Tab') {
      e.preventDefault();
      const textarea = e.currentTarget;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      
      const newContent = 
        editorContent.substring(0, start) + 
        '\t' + 
        editorContent.substring(end);
      
      setEditorContent(newContent);
      onContentChange(newContent);
      
      // Move cursor after the inserted tab
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 1;
      }, 0);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium font-mono">{fileName}</span>
          {isModified && (
            <span className="text-xs text-orange-500 font-medium">● Modified</span>
          )}
          {isReadOnly && (
            <span className="text-xs text-muted-foreground font-medium">🔒 Read-only</span>
          )}
          <span className="text-xs text-muted-foreground ml-2">{language}</span>
        </div>
        {isModified && !isReadOnly && (
          <div className="flex gap-2">
            <UIButton
              size="sm"
              variant="outline"
              onClick={onDiscard}
            >
              <RotateCcw size={14} className="mr-1" />
              Discard
            </UIButton>
            <UIButton
              size="sm"
              onClick={onSave}
            >
              <Save size={14} className="mr-1" />
              Save
            </UIButton>
          </div>
        )}
      </div>

      {/* Editor Area */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Using Textarea as fallback - can be replaced with Monaco Editor later */}
        <Textarea
          value={editorContent}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          readOnly={isReadOnly}
          className="w-full h-full font-mono text-sm resize-none border-0 rounded-none p-4"
          style={{ 
            minHeight: '100%',
            fontFamily: '"Fira Code", "Courier New", monospace',
            fontSize: '13px',
            lineHeight: '1.6',
            tabSize: 2,
            backgroundColor: isReadOnly ? 'hsl(var(--muted))' : 'hsl(var(--background))',
          }}
          placeholder="Select a file to edit..."
          spellCheck="false"
        />
      </div>

      {/* Footer Info */}
      <div className="flex items-center justify-between px-4 py-2 border-t bg-muted/20 text-xs text-muted-foreground flex-shrink-0">
        <div className="flex gap-4">
          <span>Lines: {(editorContent || '').split('\n').length}</span>
          <span>Characters: {(editorContent || '').length}</span>
        </div>
        <span>Ctrl+S to save</span>
      </div>
    </div>
  );
};
