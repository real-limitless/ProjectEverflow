import { Copy, RotateCcw, Share2, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Button } from '@patternfly/react-core';
import { ChatMessage } from '@/lib/api';

interface ResponseActionsProps {
  message: Partial<ChatMessage>;
  onRegenerate: () => Promise<void>;
  onSplit: () => Promise<void>;
  onCopy: () => void;
  onFeedback?: (isPositive: boolean) => Promise<void>;
  isLoading?: boolean;
}

export function ResponseActions({
  message,
  onRegenerate,
  onSplit,
  onCopy,
  onFeedback,
  isLoading = false,
}: ResponseActionsProps) {
  if (message.message_type !== 'assistant') {
    return null;
  }

  const handleRegenerate = async () => {
    try {
      await onRegenerate();
    } catch (error) {
      console.error('Failed to regenerate:', error);
    }
  };

  const handleSplit = async () => {
    try {
      await onSplit();
    } catch (error) {
      console.error('Failed to split thread:', error);
    }
  };

  const handleFeedback = async (isPositive: boolean) => {
    if (onFeedback) {
      try {
        await onFeedback(isPositive);
      } catch (error) {
        console.error('Failed to send feedback:', error);
      }
    }
  };

  return (
    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-200 flex-wrap">
      <Button
        variant="secondary"
        size="sm"
        icon={<RotateCcw size={14} />}
        onClick={handleRegenerate}
        isDisabled={isLoading}
        className="text-xs"
      >
        Regenerate
      </Button>

      <Button
        variant="secondary"
        size="sm"
        icon={<Share2 size={14} />}
        onClick={handleSplit}
        isDisabled={isLoading}
        className="text-xs"
      >
        Split Thread
      </Button>

      <Button
        variant="secondary"
        size="sm"
        icon={<Copy size={14} />}
        onClick={onCopy}
        isDisabled={isLoading}
        className="text-xs"
      >
        Copy
      </Button>

      {onFeedback && (
        <>
          <div className="border-l border-gray-200 mx-1 h-4" />
          <Button
            variant="plain"
            size="sm"
            icon={<ThumbsUp size={14} />}
            onClick={() => handleFeedback(true)}
            isDisabled={isLoading}
            title="Helpful"
            className="p-1 text-xs"
          />
          <Button
            variant="plain"
            size="sm"
            icon={<ThumbsDown size={14} />}
            onClick={() => handleFeedback(false)}
            isDisabled={isLoading}
            title="Not helpful"
            className="p-1 text-xs hover:text-red-600"
          />
        </>
      )}
    </div>
  );
}
