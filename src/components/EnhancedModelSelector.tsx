import { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getAvailableModels, AvailableModelsResponse, LLMProviderScope } from '@/lib/api';
import { DollarSign, Info, Loader2 } from 'lucide-react';

interface EnhancedModelSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  projectId?: number;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
  showCostEstimate?: boolean;
  estimatedTokens?: number; // For cost estimation
}

const SCOPE_COLORS: Record<LLMProviderScope, string> = {
  system: 'bg-purple-100 text-purple-800 border-purple-300',
  team: 'bg-blue-100 text-blue-800 border-blue-300',
  project: 'bg-green-100 text-green-800 border-green-300',
  user: 'bg-gray-100 text-gray-800 border-gray-300',
};

const SCOPE_LABELS: Record<LLMProviderScope, string> = {
  system: 'System',
  team: 'Team',
  project: 'Project',
  user: 'Personal',
};

export function EnhancedModelSelector({
  value,
  onValueChange,
  projectId,
  label = 'AI Model',
  placeholder = 'Select a model',
  disabled = false,
  showCostEstimate = true,
  estimatedTokens = 1000,
}: EnhancedModelSelectorProps) {
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<AvailableModelsResponse>({});
  const [selectedModelInfo, setSelectedModelInfo] = useState<{
    provider: string;
    scope: LLMProviderScope;
    pricing: { prompt_price: number; completion_price: number };
  } | null>(null);

  useEffect(() => {
    fetchModels();
  }, [projectId]);

  useEffect(() => {
    if (value && models[value]) {
      setSelectedModelInfo({
        provider: models[value].provider.name,
        scope: models[value].provider.scope,
        pricing: models[value].pricing,
      });
    } else {
      setSelectedModelInfo(null);
    }
  }, [value, models]);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const result = await getAvailableModels(projectId);
      if (result.data) {
        setModels(result.data);
      }
    } catch (error) {
      console.error('Failed to fetch models:', error);
    } finally {
      setLoading(false);
    }
  };

  // Group models by scope
  const modelsByScope: Record<LLMProviderScope, Array<[string, typeof models[string]]>> = {
    system: [],
    team: [],
    project: [],
    user: [],
  };

  Object.entries(models).forEach(([modelName, modelInfo]) => {
    modelsByScope[modelInfo.provider.scope].push([modelName, modelInfo]);
  });

  const calculateEstimatedCost = (pricing: { prompt_price: number; completion_price: number }) => {
    // Assuming 50/50 split between prompt and completion tokens
    const promptTokens = estimatedTokens * 0.5;
    const completionTokens = estimatedTokens * 0.5;
    const cost =
      (promptTokens / 1_000_000) * pricing.prompt_price +
      (completionTokens / 1_000_000) * pricing.completion_price;
    return cost;
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        {selectedModelInfo && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={SCOPE_COLORS[selectedModelInfo.scope]}>
              {SCOPE_LABELS[selectedModelInfo.scope]}
            </Badge>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground cursor-help">
                    <Info className="h-3 w-3" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-sm">Provider: {selectedModelInfo.provider}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}
      </div>

      <Select value={value} onValueChange={onValueChange} disabled={disabled || loading}>
        <SelectTrigger>
          <SelectValue placeholder={loading ? 'Loading models...' : placeholder} />
        </SelectTrigger>
        <SelectContent className="z-[9999]">
          {loading ? (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : Object.keys(models).length === 0 ? (
            <SelectItem value="_no_models" disabled>
              No models available
            </SelectItem>
          ) : (
            <>
              {/* User Models */}
              {modelsByScope.user.length > 0 && (
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Badge variant="outline" className={SCOPE_COLORS.user}>
                      My Providers
                    </Badge>
                  </SelectLabel>
                  {modelsByScope.user.map(([modelName, modelInfo]) => (
                    <SelectItem key={modelName} value={modelName}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span className="flex-1 truncate">{modelName}</span>
                        {showCostEstimate && (
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            ${(
                              (modelInfo.pricing.prompt_price + modelInfo.pricing.completion_price) /
                              2
                            ).toFixed(2)}
                            /1M
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}

              {/* Project Models */}
              {modelsByScope.project.length > 0 && (
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Badge variant="outline" className={SCOPE_COLORS.project}>
                      Project
                    </Badge>
                  </SelectLabel>
                  {modelsByScope.project.map(([modelName, modelInfo]) => (
                    <SelectItem key={modelName} value={modelName}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span className="flex-1 truncate">{modelName}</span>
                        {showCostEstimate && (
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            ${(
                              (modelInfo.pricing.prompt_price + modelInfo.pricing.completion_price) /
                              2
                            ).toFixed(2)}
                            /1M
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}

              {/* Team Models */}
              {modelsByScope.team.length > 0 && (
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Badge variant="outline" className={SCOPE_COLORS.team}>
                      Team
                    </Badge>
                  </SelectLabel>
                  {modelsByScope.team.map(([modelName, modelInfo]) => (
                    <SelectItem key={modelName} value={modelName}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span className="flex-1 truncate">{modelName}</span>
                        {showCostEstimate && (
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            ${(
                              (modelInfo.pricing.prompt_price + modelInfo.pricing.completion_price) /
                              2
                            ).toFixed(2)}
                            /1M
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}

              {/* System Models */}
              {modelsByScope.system.length > 0 && (
                <SelectGroup>
                  <SelectLabel className="flex items-center gap-2">
                    <Badge variant="outline" className={SCOPE_COLORS.system}>
                      System
                    </Badge>
                  </SelectLabel>
                  {modelsByScope.system.map(([modelName, modelInfo]) => (
                    <SelectItem key={modelName} value={modelName}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span className="flex-1 truncate">{modelName}</span>
                        {showCostEstimate && (
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            ${(
                              (modelInfo.pricing.prompt_price + modelInfo.pricing.completion_price) /
                              2
                            ).toFixed(2)}
                            /1M
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
            </>
          )}
        </SelectContent>
      </Select>

      {/* Cost Estimate Footer */}
      {selectedModelInfo && showCostEstimate && (
        <div className="flex items-center justify-between text-xs text-muted-foreground bg-muted/50 rounded px-3 py-2">
          <div className="flex items-center gap-1">
            <DollarSign className="h-3 w-3" />
            <span>Estimated cost per {estimatedTokens.toLocaleString()} tokens:</span>
          </div>
          <span className="font-mono font-semibold">
            ${calculateEstimatedCost(selectedModelInfo.pricing).toFixed(6)}
          </span>
        </div>
      )}
    </div>
  );
}
