import { useEffect, useMemo, useState } from 'react';
import { Bot, Check, Search, Star } from 'lucide-react';

import type { LLMModelOption } from '@/hooks/use-llm-models';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

interface ModelSelectorDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  selectedModelId: string;
  defaultModelLabel: string;
  models: LLMModelOption[];
  onSelectModel: (modelId: string) => void;
}

export const ModelSelectorDialog = ({
  isOpen,
  onOpenChange,
  selectedModelId,
  defaultModelLabel,
  models,
  onSelectModel,
}: ModelSelectorDialogProps) => {
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setSearchQuery('');
    }
  }, [isOpen]);

  const filteredModels = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return models;
    }

    return models.filter((model) => {
      const searchableText = [model.label, model.providerName, model.provider]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return searchableText.includes(normalizedQuery);
    });
  }, [models, searchQuery]);

  const handleSelect = (modelId: string) => {
    onSelectModel(modelId);
    onOpenChange(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>Choose AI model</DialogTitle>
          <DialogDescription>
            Search across every available model and provider, or fall back to your workspace default.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 overflow-hidden">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search models or providers..."
              className="pl-9"
            />
          </div>

          <div className="rounded-xl border border-border/80 bg-muted/20 p-2">
            <button
              type="button"
              onClick={() => handleSelect('')}
              className={`flex w-full items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors ${
                !selectedModelId ? 'bg-primary/10 text-foreground' : 'hover:bg-background'
              }`}
            >
              <div className="mt-0.5 rounded-full border border-border/70 bg-background p-2 text-muted-foreground">
                <Star className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Use workspace default model</span>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-primary">
                    Default
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{defaultModelLabel}</p>
              </div>
              {!selectedModelId && <Check className="mt-1 h-4 w-4 text-primary" />}
            </button>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{filteredModels.length} model{filteredModels.length === 1 ? '' : 's'} available</span>
            {searchQuery && <span>Filtered by “{searchQuery}”</span>}
          </div>

          <div className="space-y-2 overflow-y-auto max-h-[50vh] pr-1">
            {filteredModels.length > 0 ? (
              filteredModels.map((model) => {
                const isSelected = model.id === selectedModelId;

                return (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => handleSelect(model.id)}
                    className={`flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors ${
                      isSelected
                        ? 'border-primary bg-primary/10 text-foreground shadow-sm'
                        : 'border-border/80 bg-background hover:bg-muted/40'
                    }`}
                  >
                    <div className="mt-0.5 rounded-full border border-border/70 bg-muted/40 p-2 text-muted-foreground">
                      <Bot className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground">{model.label}</span>
                        <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                          {model.providerName}
                        </span>
                        {model.isDefault && (
                          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-amber-700">
                            User default
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                        <span>{model.provider}</span>
                        {model.contextLength ? <span>{model.contextLength.toLocaleString()} token context</span> : null}
                      </div>
                    </div>
                    {isSelected && <Check className="mt-1 h-4 w-4 text-primary" />}
                  </button>
                );
              })
            ) : (
              <div className="rounded-xl border border-dashed border-border/80 px-4 py-10 text-center text-sm text-muted-foreground">
                No models match your search.
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};