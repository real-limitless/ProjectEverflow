import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { LLMProvider, LLMProviderScope, discoverModels, updateLLMProvider } from '@/lib/api';
import { Edit, Trash2, Brain, DollarSign, RefreshCw, Eye, Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';

interface ProviderCardProps {
  provider: LLMProvider;
  usageStats?: {
    messages: number;
    cost: string;
  };
  onEdit?: (provider: LLMProvider) => void;
  onDelete?: (provider: LLMProvider) => void;
  onRefresh?: () => void;
  canEdit?: boolean;
  canDelete?: boolean;
}

const SCOPE_COLORS: Record<LLMProviderScope, string> = {
  system: 'bg-purple-100 text-purple-800 border-purple-300',
  team: 'bg-blue-100 text-blue-800 border-blue-300',
  project: 'bg-green-100 text-green-800 border-green-300',
  user: 'bg-gray-100 text-gray-800 border-gray-300',
};

const SCOPE_LABELS: Record<LLMProviderScope, string> = {
  system: 'System-Wide',
  team: 'Team',
  project: 'Project',
  user: 'Personal',
};

const PROVIDER_ICONS: Record<string, string> = {
  openai: '🤖',
  anthropic: '🧠',
  openrouter: '🔀',
  vllm: '⚡',
  ollama: '🦙',
  litemaas: '🔧',
};

export function ProviderCard({
  provider,
  usageStats,
  onEdit,
  onDelete,
  onRefresh,
  canEdit = true,
  canDelete = true,
}: ProviderCardProps) {
  const { toast } = useToast();
  const [discovering, setDiscovering] = useState(false);
  const [showModels, setShowModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  
  const modelCount = Array.isArray(provider.available_models) 
    ? provider.available_models.length 
    : Object.keys(provider.available_models || {}).length;
  const providerIcon = PROVIDER_ICONS[provider.provider_type] || '🔌';

  // Parse models into a normalized format
  const allModels = Array.isArray(provider.available_models)
    ? provider.available_models.map((m: any) => ({
        id: typeof m === 'string' ? m : (m.id || m.name),
        name: typeof m === 'string' ? m : (m.name || m.id),
        context_length: typeof m === 'object' ? m.context_length : undefined,
        pricing: typeof m === 'object' ? m.pricing : undefined,
      }))
    : Object.entries(provider.available_models || {}).map(([id, data]: [string, any]) => ({
        id,
        name: id,
        context_length: data.context_length,
        pricing: data.pricing,
      }));

  // Filter models based on search
  const filteredModels = allModels.filter((model: any) =>
    model.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleDiscoverModels = async () => {
    setDiscovering(true);
    try {
      const result = await discoverModels(provider.id);
      if (result.data) {
        toast({
          title: 'Models Discovered',
          description: `Found ${result.data.models.length} models`,
        });
        if (onRefresh) onRefresh();
      } else if (result.error) {
        throw new Error(result.error);
      }
    } catch (error: any) {
      toast({
        title: 'Discovery Failed',
        description: error.message || 'Failed to discover models',
        variant: 'destructive',
      });
    } finally {
      setDiscovering(false);
    }
  };

  const handleOpenModels = () => {
    // Initialize selected models with currently available ones
    const currentModelIds = new Set(allModels.map((m: any) => m.id));
    setSelectedModels(currentModelIds);
    setShowModels(true);
  };

  const handleToggleModel = (modelId: string) => {
    const newSelected = new Set(selectedModels);
    if (newSelected.has(modelId)) {
      newSelected.delete(modelId);
    } else {
      newSelected.add(modelId);
    }
    setSelectedModels(newSelected);
  };

  const handleSelectAll = () => {
    setSelectedModels(new Set(filteredModels.map((m: any) => m.id)));
  };

  const handleDeselectAll = () => {
    setSelectedModels(new Set());
  };

  const handleSaveSelection = async () => {
    setSaving(true);
    try {
      // Filter to only include selected models
      const enabledModels = allModels.filter((m: any) => selectedModels.has(m.id));
      
      // Preserve scope fields when updating
      const updateData: any = {
        available_models: enabledModels,
      };
      
      if (provider.scope === 'user' && provider.scope_user) {
        updateData.scope_user = provider.scope_user;
      } else if (provider.scope === 'team' && provider.scope_team) {
        updateData.scope_team = provider.scope_team;
      } else if (provider.scope === 'project' && provider.scope_project) {
        updateData.scope_project = provider.scope_project;
      }
      
      const result = await updateLLMProvider(provider.id, updateData);

      if (result.error) {
        throw new Error(result.error);
      }

      toast({
        title: 'Models Updated',
        description: `${selectedModels.size} models enabled for use`,
      });

      setShowModels(false);
      if (onRefresh) onRefresh();
    } catch (error: any) {
      toast({
        title: 'Update Failed',
        description: error.message || 'Failed to update model selection',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="relative">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <div className="text-3xl">{providerIcon}</div>
            <div className="flex-1">
              <CardTitle className="text-lg">{provider.instance_name}</CardTitle>
              <CardDescription className="capitalize">{provider.provider_type}</CardDescription>
            </div>
          </div>
          <div className="flex gap-2">
            {canEdit && onEdit && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onEdit(provider)}
                className="h-8 w-8 p-0"
              >
                <Edit className="h-4 w-4" />
              </Button>
            )}
            {canDelete && onDelete && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDelete(provider)}
                className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Scope Badge */}
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={SCOPE_COLORS[provider.scope]}>
              {SCOPE_LABELS[provider.scope]}
            </Badge>
          </div>

          {/* Model Count */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Brain className="h-4 w-4" />
            <span>
              {modelCount > 0 ? `${modelCount} models available` : 'No models discovered'}
            </span>
          </div>

          {/* Usage Stats */}
          {usageStats && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <DollarSign className="h-4 w-4" />
              <span>
                {usageStats.messages} messages • ${parseFloat(usageStats.cost).toFixed(4)} spent (30d)
              </span>
            </div>
          )}

          {/* API Key Preview */}
          <div className="text-xs text-muted-foreground font-mono">
            {provider.api_key}
          </div>

          {/* Base URL (if custom) */}
          {provider.base_url && (
            <div className="text-xs text-muted-foreground">
              <span className="font-semibold">URL:</span> {provider.base_url}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDiscoverModels}
              disabled={discovering}
              className="flex-1"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${discovering ? 'animate-spin' : ''}`} />
              {discovering ? 'Discovering...' : 'Discover Models'}
            </Button>
            {modelCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenModels}
                className="flex-1"
              >
                <Eye className="h-4 w-4 mr-2" />
                Manage Models
              </Button>
            )}
          </div>
        </div>
      </CardContent>

      {/* Models Dialog */}
      <Dialog open={showModels} onOpenChange={setShowModels}>
        <DialogContent className="sm:max-w-[800px] max-h-[85vh]">
          <DialogHeader>
            <DialogTitle>Manage Models - {provider.instance_name}</DialogTitle>
            <DialogDescription>
              Select which models to enable for use in projects and chatbots
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            {/* Search and Actions */}
            <div className="flex gap-2 items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search models..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Button variant="outline" size="sm" onClick={handleSelectAll}>
                Select All
              </Button>
              <Button variant="outline" size="sm" onClick={handleDeselectAll}>
                Deselect All
              </Button>
            </div>

            {/* Selected Count */}
            <div className="text-sm text-muted-foreground">
              {selectedModels.size} of {allModels.length} models selected
            </div>

            {/* Models List */}
            <div className="space-y-2 overflow-y-auto max-h-[50vh] pr-2">
              {filteredModels.length > 0 ? (
                filteredModels.map((model: any) => (
                  <div
                    key={model.id}
                    className="flex items-start gap-3 p-3 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => handleToggleModel(model.id)}
                  >
                    <Checkbox
                      checked={selectedModels.has(model.id)}
                      onCheckedChange={() => handleToggleModel(model.id)}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{model.name}</div>
                      {model.context_length && (
                        <div className="text-xs text-muted-foreground mt-1">
                          Context: {model.context_length.toLocaleString()} tokens
                        </div>
                      )}
                    </div>
                    {model.pricing && (
                      <div className="text-right text-xs shrink-0">
                        <div className="text-muted-foreground">
                          ${(model.pricing.prompt * 1000).toFixed(4)}/1K in
                        </div>
                        <div className="text-muted-foreground">
                          ${(model.pricing.completion * 1000).toFixed(4)}/1K out
                        </div>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  {searchQuery ? 'No models match your search' : 'No models available'}
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModels(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSaveSelection} disabled={saving || selectedModels.size === 0}>
              {saving ? 'Saving...' : `Enable ${selectedModels.size} Model${selectedModels.size !== 1 ? 's' : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
