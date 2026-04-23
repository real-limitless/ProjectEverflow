import { useQuery } from '@tanstack/react-query';
import { getCurrentUser, getAvailableModels, LLMProvider } from '@/lib/api';

export interface LLMModelOption {
  id: string;
  label: string;
  provider: string;
  providerName: string;
  isDefault: boolean;
  pricing?: {
    prompt: number;
    completion: number;
  };
  contextLength?: number;
}

export interface UseLLMModelsResult {
  models: LLMModelOption[];
  defaultModel: string | null;
  isLoading: boolean;
  getEffectiveModel: (selectedModel: string | null) => string | null;
  getModelLabel: (modelId: string | null) => string;
}

/**
 * Hook to manage LLM models with user default preference
 * Fetches available models from providers and returns them with default highlighted
 */
export function useLLMModels(projectId?: number): UseLLMModelsResult {
  // Fetch current user to get default_llm_model
  const { data: userResponse } = useQuery({
    queryKey: ['current-user'],
    queryFn: getCurrentUser,
  });

  const user = userResponse?.data;
  const defaultModel = user?.default_llm_model || null;

  // Fetch available models from providers
  const { data: modelsResponse, isLoading } = useQuery({
    queryKey: ['available-models', projectId],
    queryFn: () => getAvailableModels(projectId),
  });

  const availableModels = modelsResponse?.data || {};

  // Transform models into LLMModelOption format
  const models: LLMModelOption[] = Object.entries(availableModels)
    .filter(([_, modelData]: [string, any]) => modelData && modelData.provider)
    .map(([modelId, modelData]: [string, any]) => {
      const provider = modelData.provider as LLMProvider;
      return {
        id: modelId,
        label: modelId,
        provider: provider.provider_type,
        providerName: provider.instance_name,
        isDefault: modelId === defaultModel,
        pricing: modelData.pricing,
        contextLength: modelData.context_length,
      };
    });

  // Sort models: default first, then alphabetically
  models.sort((a, b) => {
    if (a.isDefault && !b.isDefault) return -1;
    if (!a.isDefault && b.isDefault) return 1;
    return a.label.localeCompare(b.label);
  });

  /**
   * Get the effective model to use (selected or default)
   */
  const getEffectiveModel = (selectedModel: string | null): string | null => {
    if (selectedModel && selectedModel !== '') return selectedModel;
    return defaultModel;
  };

  /**
   * Get display label for a model ID
   */
  const getModelLabel = (modelId: string | null): string => {
    if (!modelId) return 'Use Default Model';
    const model = models.find(m => m.id === modelId);
    if (!model) return modelId;
    
    const label = `${model.label} (${model.providerName})`;
    return model.isDefault ? `${label} ⭐ Default` : label;
  };

  return {
    models,
    defaultModel,
    isLoading,
    getEffectiveModel,
    getModelLabel,
  };
}
