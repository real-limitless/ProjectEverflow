import React, { useState, useEffect } from 'react';
import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, User, Briefcase, Code, Heart, Lightbulb } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getAvailableLLMs, getChatbotPersona } from '@/lib/api';
import { LLMModelOption } from '@/hooks/use-llm-models';

interface PersonaSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (settings: { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }) => void;
  initialSettings: { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string };
  personaId: string | null;
  templatesData?: any[]; // No longer used, but kept for compatibility if needed
  availableModels?: LLMModelOption[];
  defaultModel?: string | null;
  getModelLabel?: (modelId: string | null) => string;
}

export default function PersonaSettingsModal({
  isOpen,
  onClose,
  onSave,
  initialSettings,
  personaId,
  templatesData = [],
  availableModels = [],
  defaultModel = null,
  getModelLabel = (modelId) => modelId || 'Use Default Model',
}: PersonaSettingsModalProps) {
  const [llm, setLlm] = useState<string | null>(initialSettings.llm);
  const [temperature, setTemperature] = useState<number>(initialSettings.temperature);
  const [maxTokens, setMaxTokens] = useState<number>(initialSettings.maxTokens);
  const [prompt, setPrompt] = useState<string>(initialSettings.prompt);
  const [description, setDescription] = useState<string>(initialSettings.description);
  const [name, setName] = useState<string>(initialSettings.name);
  const [icon, setIcon] = useState<string>(initialSettings.icon);

  // Fetch available LLMs from backend
  const { data: availableLLMs, isLoading: llmsLoading } = useQuery({
    queryKey: ['available-llms'],
    queryFn: () => getAvailableLLMs(),
    select: (response) => response.data?.llms || [], // response.data is LLMConfigResponse with llms array
  });

  // Fetch current persona data from backend
  const { data: personaData, isLoading: personaLoading } = useQuery({
    queryKey: ['chatbot-persona', personaId],
    queryFn: () => personaId ? getChatbotPersona(parseInt(personaId)) : Promise.resolve(null),
    select: (response) => response?.data,
    enabled: !!personaId && isOpen,
  });

  useEffect(() => {
    if (isOpen) {
      // Set initial values from props
      setLlm(initialSettings.llm);
      setTemperature(initialSettings.temperature);
      setMaxTokens(initialSettings.maxTokens);
      setPrompt(initialSettings.prompt);
      setDescription(initialSettings.description);
      setName(initialSettings.name);
      setIcon(initialSettings.icon);
    }
  }, [isOpen, initialSettings]);

  // Update persona-specific fields when backend data loads
  useEffect(() => {
    if (personaData) {
      setPrompt(personaData.system_prompt || '');
      setDescription(personaData.description || '');
      setName(personaData.name || '');
      setIcon(personaData.icon || '');
    }
  }, [personaData]);

  const handleSave = () => {
    onSave({ llm, temperature, maxTokens, prompt, description, name, icon });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium">
      <ModalHeader>Persona Settings</ModalHeader>
      <ModalBody>
        {personaLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span className="ml-2 text-sm text-muted-foreground">Loading persona settings...</span>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-6">
            {/* Left Column: Persona Info & Model Settings */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="name-input">Persona Name</Label>
                <Input
                  id="name-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Enter persona name..."
                />
              </div>
              <div>
                <Label htmlFor="icon-select">Persona Icon</Label>
                <Select value={icon} onValueChange={setIcon}>
                  <SelectTrigger id="icon-select">
                    <SelectValue placeholder="Select an icon" />
                  </SelectTrigger>
                  <SelectContent className="z-[9999]">
                    <SelectItem value="User">
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4" />
                        User
                      </div>
                    </SelectItem>
                    <SelectItem value="Briefcase">
                      <div className="flex items-center gap-2">
                        <Briefcase className="h-4 w-4" />
                        Briefcase
                      </div>
                    </SelectItem>
                    <SelectItem value="Code">
                      <div className="flex items-center gap-2">
                        <Code className="h-4 w-4" />
                        Code
                      </div>
                    </SelectItem>
                    <SelectItem value="Heart">
                      <div className="flex items-center gap-2">
                        <Heart className="h-4 w-4" />
                        Heart
                      </div>
                    </SelectItem>
                    <SelectItem value="Lightbulb">
                      <div className="flex items-center gap-2">
                        <Lightbulb className="h-4 w-4" />
                        Lightbulb
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="llm-select">AI Model</Label>
                <Select value={llm || ''} onValueChange={(value) => setLlm(value || null)}>
                  <SelectTrigger id="llm-select">
                    <SelectValue placeholder={defaultModel ? getModelLabel(null) : "Select a model"} />
                  </SelectTrigger>
                  <SelectContent className="z-[9999]">
                    <SelectItem value="">
                      {defaultModel ? `⭐ ${getModelLabel(null)}` : 'No Default Set'}
                    </SelectItem>
                    {availableModels.length > 0 ? (
                      availableModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.isDefault ? '⭐ ' : ''}{model.label} ({model.providerName})
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="no-models" disabled>
                        No models configured
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="temperature-slider">Temperature: {temperature}</Label>
                <Slider
                  id="temperature-slider"
                  min={0}
                  max={2}
                  step={0.1}
                  value={[temperature]}
                  onValueChange={(value) => setTemperature(value[0])}
                  className="mt-2"
                />
              </div>
              <div>
                <Label htmlFor="max-tokens-input">Max Tokens</Label>
                <Input
                  id="max-tokens-input"
                  type="number"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(parseInt(e.target.value) || 1000)}
                  min={1}
                  max={4096}
                />
              </div>
            </div>

            {/* Right Column: AI Instruction Prompt */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="description-textarea">AI Persona Description</Label>
                <Textarea
                  id="description-textarea"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Enter a short description for the AI persona..."
                  className="min-h-[100px] resize-none"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  This description will be displayed under the persona.
                </p>
              </div>
              <div>
                <Label htmlFor="prompt-textarea">AI Instruction Prompt</Label>
                <Textarea
                  id="prompt-textarea"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter custom instructions for the AI persona..."
                  className="min-h-[200px] resize-none"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  This prompt guides the AI's responses. Be specific about the persona's role and behavior.
                </p>
              </div>
            </div>
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleSave}>
          Save Settings
        </Button>
      </ModalFooter>
    </Modal>
  );
}