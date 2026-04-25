import React, { useState } from 'react';
import { Badge, Button, Card, CardBody } from '@patternfly/react-core';
import { ScrollArea } from '@/components/ui/scroll-area';
import { User, Briefcase, Code, Heart, Lightbulb, Plus, Loader2, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { getChatbotPersonas, updateChatbotPersona, ChatbotPersona } from '@/lib/api';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/hooks/use-toast';
import PersonaSettingsModal from './PersonaSettingsModal';

const getIconComponent = (iconName: string) => {
  switch (iconName) {
    case 'User': return User;
    case 'Briefcase': return Briefcase;
    case 'Code': return Code;
    case 'Heart': return Heart;
    case 'Lightbulb': return Lightbulb;
    default: return User;
  }
};

interface PersonaSelectorProps {
  selectedPersona: string | null;
  onPersonaSelect: (personaId: string) => void;
  onCreatePersona: () => void;
  personasData?: any[];
  personaSettings?: Record<string, { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }>;
  onPersonaSettingsChange?: (personaId: string, settings: { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }) => void;
  templatesData?: any[];
  availableModels?: LLMModelOption[];
  defaultModel?: string | null;
  getModelLabel?: (modelId: string | null) => string;
}

export const PersonaSelector: React.FC<PersonaSelectorProps> = ({
  selectedPersona, 
  onPersonaSelect, 
  onCreatePersona,
  personasData,
  personaSettings = {},
  onPersonaSettingsChange,
  templatesData = [],
  availableModels = [],
  defaultModel = null,
  getModelLabel = (modelId) => modelId || 'Use Default Model',
}) => {
  const queryClient = useQueryClient();
  const { data: personas, isLoading, error } = useQuery({
    queryKey: ['chatbot-personas'],
    queryFn: () => getChatbotPersonas(),
    select: (response) => response.data,
  });

  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [currentPersonaId, setCurrentPersonaId] = useState<string | null>(null);



  const handleSettingsClick = (personaId: string) => {
    setCurrentPersonaId(personaId);
    setSettingsModalOpen(true);
  };

  const getInitialSettings = (personaId: string) => {
    const settings = personaSettings[personaId];
    const persona = personasData?.find(p => p.id.toString() === personaId);
    
    return {
      llm: settings?.llm ?? persona?.default_llm_id ?? null,
      temperature: settings?.temperature ?? persona?.default_temperature ?? 0.7,
      maxTokens: settings?.maxTokens ?? persona?.default_max_tokens ?? 1000,
      prompt: settings?.prompt || persona?.system_prompt || '',
      description: settings?.description || persona?.description || '',
      name: settings?.name || persona?.name || '',
      icon: settings?.icon || persona?.icon || '',
    };
  };

  const handleSettingsSave = async (settings: { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }) => {
    if (currentPersonaId && onPersonaSettingsChange) {
      onPersonaSettingsChange(currentPersonaId, settings);
    }

    // Update persona in backend if prompt, description, name, or icon changed
    if (currentPersonaId) {
      const personaId = parseInt(currentPersonaId);
      const persona = personasData?.find(p => p.id.toString() === currentPersonaId);
      const currentSettings = personaSettings[currentPersonaId] || { 
        prompt: persona?.system_prompt || '', 
        description: persona?.description || '',
        name: persona?.name || '',
        icon: persona?.icon || ''
      };

      const updates: Partial<ChatbotPersona> = {};
      if (settings.prompt !== currentSettings.prompt) {
        updates.system_prompt = settings.prompt;
      }
      if (settings.description !== currentSettings.description) {
        updates.description = settings.description;
      }
      if (settings.name !== currentSettings.name) {
        updates.name = settings.name;
      }
      if (settings.icon !== currentSettings.icon) {
        updates.icon = settings.icon;
      }
      if (settings.llm !== (persona?.default_llm_id ?? null)) {
        updates.default_llm_id = settings.llm;
      }
      if (settings.temperature !== (persona?.default_temperature ?? 0.7)) {
        updates.default_temperature = settings.temperature;
      }
      if (settings.maxTokens !== (persona?.default_max_tokens ?? 1000)) {
        updates.default_max_tokens = settings.maxTokens;
      }

      if (Object.keys(updates).length > 0) {
        try {
          await updateChatbotPersona(personaId, updates);
          toast({
            title: "Persona Updated",
            description: "Persona settings have been saved to the backend.",
          });
          // Invalidate personas query to refresh data
          queryClient.invalidateQueries({ queryKey: ['chatbot-personas'] });
        } catch (error) {
          toast({
            title: "Error",
            description: "Failed to update persona in backend.",
            variant: "destructive",
          });
        }
      }
    }

    setSettingsModalOpen(false);
  };

  if (error) {
    toast({
      title: "Error loading personas",
      description: "Failed to load AI personas. Please try again.",
      variant: "destructive",
    });
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold">AI Personas</h3>
          <Button size="sm" variant="secondary" onClick={onCreatePersona}>
            <Plus size={14} className="mr-1" />
            Create
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Choose an AI persona for specialized assistance
        </p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2 text-sm text-muted-foreground">Loading personas...</span>
            </div>
          ) : personas && personas.length > 0 ? (
            <div className="space-y-2">
              {personas.map((persona) => {
                const customSettings = personaSettings[persona.id];
                const displayName = customSettings?.name || persona.name;
                const displayIcon = customSettings?.icon || persona.icon;
                const displayDescription = customSettings?.description || persona.description;
                const displayPrompt = customSettings?.prompt || persona.system_prompt;
                const Icon = getIconComponent(displayIcon);
                return (
                                    <Card
                    className={`cursor-pointer transition-all hover:border-primary hover:bg-muted/50 ${
                      selectedPersona === persona.id.toString() && "border-primary bg-muted"
                    }`}
                    onClick={() => onPersonaSelect(persona.id.toString())}
                    style={{ border: '1px solid var(--pf-v6-global--BorderColor--100)' }}
                  >
                    <CardBody className="p-3">
                      <div className="flex items-start gap-3">
                        <div className="p-2 rounded-md bg-primary/10">
                          <Icon className="h-4 w-4 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="text-sm font-medium truncate">{displayName}</p>
                            <Badge variant="secondary" className="text-xs">
                              {persona.category}
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-2 mb-2">
                            {displayDescription}
                          </p>
                          {persona.system_prompt && (
                            <div className="mb-2">
                              <p className="text-xs font-medium text-muted-foreground mb-1">Instructions:</p>
                              <p className="text-xs text-muted-foreground line-clamp-3 bg-muted/50 p-2 rounded">
                                {displayPrompt}
                              </p>
                            </div>
                          )}

                          <div className="flex justify-end">
                            <Button
                              size="sm"
                              variant="plain"
                              className="h-7 w-7 p-0"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSettingsClick(persona.id.toString());
                              }}
                              aria-label={`Settings for ${displayName}`}
                            >
                              <Settings size={14} />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </CardBody>
                  </Card>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground">No personas available</p>
            </div>
          )}
        </div>
      </ScrollArea>

      {currentPersonaId && (
        <PersonaSettingsModal
          isOpen={settingsModalOpen}
          onClose={() => setSettingsModalOpen(false)}
          onSave={handleSettingsSave}
          initialSettings={getInitialSettings(currentPersonaId)}
          personaId={currentPersonaId}
          templatesData={templatesData}
          availableModels={availableModels}
          defaultModel={defaultModel}
          getModelLabel={getModelLabel}
        />
      )}
    </div>
  );
};
