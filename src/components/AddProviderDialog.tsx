import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import {
  LLMProviderScope,
  LLMProviderType,
  LLMProvider,
  createLLMProvider,
  updateLLMProvider,
  testConnection,
  discoverModels,
  User,
} from '@/lib/api';
import { Loader2, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react';

interface AddProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
  currentUser: User;
  teams: Array<{ id: number; name: string }>;
  projects: Array<{ id: number; name: string }>;
  editProvider?: LLMProvider | null;
}

const PROVIDER_TYPES: Array<{ value: LLMProviderType; label: string; requiresUrl: boolean; defaultUrl?: string }> = [
  { value: 'openai', label: 'OpenAI', requiresUrl: false, defaultUrl: 'https://api.openai.com/v1' },
  { value: 'anthropic', label: 'Anthropic', requiresUrl: false, defaultUrl: 'https://api.anthropic.com' },
  { value: 'openrouter', label: 'OpenRouter', requiresUrl: false, defaultUrl: 'https://openrouter.ai/api/v1' },
  { value: 'vllm', label: 'vLLM (Self-Hosted)', requiresUrl: true },
  { value: 'ollama', label: 'Ollama (Local)', requiresUrl: true, defaultUrl: 'http://localhost:11434' },
  { value: 'litemaas', label: 'LiteMaaS (Legacy)', requiresUrl: false },
];

export function AddProviderDialog({
  open,
  onOpenChange,
  onSuccess,
  currentUser,
  teams,
  projects,
  editProvider,
}: AddProviderDialogProps) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message?: string } | null>(null);

  // Form state
  const [scope, setScope] = useState<LLMProviderScope>(editProvider?.scope || 'user');
  const [name, setName] = useState(editProvider?.instance_name || '');
  const [providerType, setProviderType] = useState<LLMProviderType>(
    editProvider?.provider_type || 'openai'
  );
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(editProvider?.base_url || '');
  const [teamId, setTeamId] = useState<number | undefined>(editProvider?.scope_team);
  const [projectId, setProjectId] = useState<number | undefined>(editProvider?.scope_project);

  const isAdmin = currentUser.role === 'admin';
  const isEdit = !!editProvider;

  // Available scopes based on permissions
  const availableScopes: Array<{ value: LLMProviderScope; label: string }> = [
    { value: 'user', label: 'Personal (My Providers)' },
    ...(projects.length > 0 && isAdmin
      ? [{ value: 'project' as LLMProviderScope, label: 'Project-Wide' }]
      : []),
    ...(teams.length > 0 && isAdmin
      ? [{ value: 'team' as LLMProviderScope, label: 'Team-Wide' }]
      : []),
    ...(isAdmin ? [{ value: 'system' as LLMProviderScope, label: 'System-Wide (All Users)' }] : []),
  ];

  const selectedProviderConfig = PROVIDER_TYPES.find((p) => p.value === providerType);

  const handleTestConnection = async () => {
    if (!apiKey && !isEdit) {
      toast({
        title: 'API Key Required',
        description: 'Please enter an API key to test the connection.',
        variant: 'destructive',
      });
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      // If editing and no new API key, test the existing provider
      if (isEdit && !apiKey) {
        const result = await testConnection(editProvider.id);
        if (result.data) {
          setTestResult(result.data);
          toast({
            title: result.data.success ? 'Connection Successful' : 'Connection Failed',
            description: result.data.message || (result.data.success ? 'Provider is reachable' : 'Unable to reach provider'),
            variant: result.data.success ? 'default' : 'destructive',
          });
        }
      } else {
        // For new providers, we need to create a temporary provider to test
        // This is a limitation - ideally backend should support test without saving
        toast({
          title: 'Test Connection',
          description: 'Please save the provider first to test connection.',
          variant: 'default',
        });
      }
    } catch (error: any) {
      toast({
        title: 'Test Failed',
        description: error.message || 'Failed to test connection',
        variant: 'destructive',
      });
      setTestResult({ success: false, message: error.message });
    } finally {
      setTesting(false);
    }
  };

  const handleDiscoverModels = async () => {
    if (!editProvider) {
      toast({
        title: 'Save Provider First',
        description: 'Please save the provider before discovering models.',
        variant: 'default',
      });
      return;
    }

    setDiscovering(true);

    try {
      const result = await discoverModels(editProvider.id);
      if (result.data) {
        toast({
          title: 'Models Discovered',
          description: `Found ${result.data.models.length} models for ${name}`,
        });
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!name.trim()) {
      toast({
        title: 'Name Required',
        description: 'Please enter a name for this provider.',
        variant: 'destructive',
      });
      return;
    }

    if (!isEdit && !apiKey.trim()) {
      toast({
        title: 'API Key Required',
        description: 'Please enter an API key.',
        variant: 'destructive',
      });
      return;
    }

    if (selectedProviderConfig?.requiresUrl && !baseUrl.trim() && !selectedProviderConfig?.defaultUrl) {
      toast({
        title: 'Base URL Required',
        description: `${selectedProviderConfig.label} requires a base URL.`,
        variant: 'destructive',
      });
      return;
    }

    if (scope === 'team' && !teamId) {
      toast({
        title: 'Team Required',
        description: 'Please select a team for team-wide scope.',
        variant: 'destructive',
      });
      return;
    }

    if (scope === 'project' && !projectId) {
      toast({
        title: 'Project Required',
        description: 'Please select a project for project-wide scope.',
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);

    try {
      if (isEdit) {
        // Update existing provider
        const updateData: any = { instance_name: name };
        if (apiKey) updateData.api_key_plain = apiKey;
        
        // Use provided URL or default for provider type
        const urlToUse = baseUrl.trim() || selectedProviderConfig?.defaultUrl || '';
        if (urlToUse) updateData.base_url = urlToUse;

        const result = await updateLLMProvider(editProvider.id, updateData);
        if (result.error) {
          throw new Error(result.error);
        }

        toast({
          title: 'Provider Updated',
          description: `Successfully updated ${name}`,
        });
      } else {
        // Create new provider
        const createData: any = {
          scope,
          instance_name: name.trim(),
          provider_type: providerType,
          api_key_plain: apiKey.trim(),
        };

        // Use provided URL or default for provider type
        const urlToUse = baseUrl.trim() || selectedProviderConfig?.defaultUrl || '';
        if (urlToUse) createData.base_url = urlToUse;
        
        if (scope === 'user') createData.scope_user = currentUser.id;
        if (scope === 'team' && teamId) createData.scope_team = teamId;
        if (scope === 'project' && projectId) createData.scope_project = projectId;

        const result = await createLLMProvider(createData);
        if (result.error) {
          throw new Error(result.error);
        }

        toast({
          title: 'Provider Created',
          description: `Successfully created ${name}`,
        });
      }

      onSuccess();
      onOpenChange(false);
      
      // Reset form
      setScope('user');
      setName('');
      setProviderType('openai');
      setApiKey('');
      setBaseUrl('');
      setTeamId(undefined);
      setProjectId(undefined);
      setTestResult(null);
    } catch (error: any) {
      toast({
        title: isEdit ? 'Update Failed' : 'Creation Failed',
        description: error.message || `Failed to ${isEdit ? 'update' : 'create'} provider`,
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit' : 'Add'} LLM Provider</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update provider configuration and API credentials.'
              : 'Configure a new LLM provider for AI interactions.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Provider Type */}
          {!isEdit && (
            <div className="space-y-2">
              <Label htmlFor="provider-type">Provider Type</Label>
              <Select value={providerType} onValueChange={(v) => setProviderType(v as LLMProviderType)}>
                <SelectTrigger id="provider-type">
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDER_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Scope */}
          {!isEdit && (
            <div className="space-y-2">
              <Label htmlFor="scope">Scope</Label>
              <Select value={scope} onValueChange={(v) => setScope(v as LLMProviderScope)}>
                <SelectTrigger id="scope">
                  <SelectValue placeholder="Select scope" />
                </SelectTrigger>
                <SelectContent>
                  {availableScopes.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Team Selection */}
          {scope === 'team' && !isEdit && (
            <div className="space-y-2">
              <Label htmlFor="team">Team</Label>
              <Select value={teamId?.toString()} onValueChange={(v) => setTeamId(parseInt(v))}>
                <SelectTrigger id="team">
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent>
                  {teams.map((team) => (
                    <SelectItem key={team.id} value={team.id.toString()}>
                      {team.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Project Selection */}
          {scope === 'project' && !isEdit && (
            <div className="space-y-2">
              <Label htmlFor="project">Project</Label>
              <Select value={projectId?.toString()} onValueChange={(v) => setProjectId(parseInt(v))}>
                <SelectTrigger id="project">
                  <SelectValue placeholder="Select project" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((project) => (
                    <SelectItem key={project.id} value={project.id.toString()}>
                      {project.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="e.g., GPT-4 Production"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          {/* API Key */}
          <div className="space-y-2">
            <Label htmlFor="api-key">
              API Key {isEdit && <span className="text-sm text-muted-foreground">(leave blank to keep existing)</span>}
            </Label>
            <div className="relative">
              <Input
                id="api-key"
                type={showApiKey ? 'text' : 'password'}
                placeholder={isEdit ? '********' : 'sk-...'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required={!isEdit}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          {/* Base URL */}
          {selectedProviderConfig?.requiresUrl && (
            <div className="space-y-2">
              <Label htmlFor="base-url">Base URL</Label>
              <Input
                id="base-url"
                placeholder={providerType === 'ollama' ? 'http://localhost:11434' : 'https://your-vllm-server.com'}
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                required
              />
            </div>
          )}

          {/* Test Result */}
          {testResult && (
            <div
              className={`flex items-center gap-2 rounded-md border p-3 ${
                testResult.success ? 'border-green-500 bg-green-50' : 'border-red-500 bg-red-50'
              }`}
            >
              {testResult.success ? (
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              <span className="text-sm">{testResult.message || (testResult.success ? 'Connection successful!' : 'Connection failed')}</span>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={handleTestConnection} disabled={testing || loading}>
              {testing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Testing...
                </>
              ) : (
                'Test Connection'
              )}
            </Button>

            {isEdit && (
              <Button type="button" variant="outline" onClick={handleDiscoverModels} disabled={discovering || loading}>
                {discovering ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Discovering...
                  </>
                ) : (
                  'Discover Models'
                )}
              </Button>
            )}

            <Button type="submit" disabled={loading || testing || discovering}>
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isEdit ? 'Updating...' : 'Creating...'}
                </>
              ) : (
                isEdit ? 'Update Provider' : 'Create Provider'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
