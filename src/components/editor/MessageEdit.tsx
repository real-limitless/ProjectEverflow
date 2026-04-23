import { useState } from 'react';
import { Edit2, X, Check, Copy, Trash2 } from 'lucide-react';
import { Button } from '@patternfly/react-core';
import { TextArea } from '@patternfly/react-core';
import { ChatMessage } from '@/lib/api';

interface MessageEditProps {
  message: Partial<ChatMessage>;
  isEditing: boolean;
  onEdit: () => void;
  onSave: (content: string) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => Promise<void>;
  onCopy?: () => void;
  isSaving?: boolean;
}

export function MessageEdit({
  message,
  isEditing,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  onCopy,
  isSaving = false,
}: MessageEditProps) {
  const [editContent, setEditContent] = useState(message.content || '');

  const handleSave = async () => {
    if (!editContent.trim()) return;
    try {
      await onSave(editContent);
    } catch (error) {
      console.error('Failed to save message:', error);
    }
  };

  if (isEditing) {
    return (
      <div className="space-y-2 w-full">
        <TextArea
          value={editContent}
          onChange={(_, value) => setEditContent(value)}
          placeholder="Edit message..."
          resizeOrientation="vertical"
          className="min-h-20 w-full"
        />
        <div className="flex items-center gap-2 justify-end">
          <Button
            variant="secondary"
            size="sm"
            icon={<X size={14} />}
            onClick={onCancel}
            isDisabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Check size={14} />}
            onClick={handleSave}
            isDisabled={isSaving || !editContent.trim()}
          >
            {isSaving ? 'Saving...' : 'Save & Resend'}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      {message.message_type === 'user' && (
        <Button
          variant="plain"
          size="sm"
          icon={<Edit2 size={14} />}
          onClick={onEdit}
          title="Edit message"
          className="p-1"
        />
      )}
      {onCopy && (
        <Button
          variant="plain"
          size="sm"
          icon={<Copy size={14} />}
          onClick={onCopy}
          title="Copy message"
          className="p-1"
        />
      )}
      {onDelete && (
        <Button
          variant="plain"
          size="sm"
          icon={<Trash2 size={14} />}
          onClick={onDelete}
          title="Delete message"
          className="p-1 hover:text-red-600"
        />
      )}
    </div>
  );
}
