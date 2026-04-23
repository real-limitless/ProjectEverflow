import { useState } from 'react';
import { Page, PageSection, Card, CardBody } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ChatInterface } from '@/components/chatbot/ChatInterface';
import { PersonaSelector } from '@/components/chatbot/PersonaSelector';
import { TemplateManager } from '@/components/chatbot/TemplateManager';
import { ChatHistory } from '@/components/chatbot/ChatHistory';
import { TemplateVariableDialog } from '@/components/chatbot/TemplateVariableDialog';
import { MessageSquare } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import { useLLMModels } from '@/hooks/use-llm-models';
import { useQueryClient } from '@tanstack/react-query';
import { createChatSession, ChatbotTemplate, sendChatMessage } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';

// Import template data to get variable information
import personasData from '@/data/chatbotPersonas.json';

// Helper function to apply template variables
const applyTemplateVariables = (template: ChatbotTemplate, variables: Record<string, string>): string => {
  let message = template.user_prompt_template || '';
  Object.entries(variables).forEach(([key, value]) => {
    message = message.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
  });
  return message;
};

const EnterpriseChatbot = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [templateVariables, setTemplateVariables] = useState<Record<string, string>>({});
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [isVariableDialogOpen, setIsVariableDialogOpen] = useState(false);
  const [pendingTemplate, setPendingTemplate] = useState<{
    id: string;
    variables: string[];
    name: string;
    template: ChatbotTemplate;
  } | null>(null);
  const [selectedLLM, setSelectedLLM] = useState<string | null>(null);
  const [temperature, setTemperature] = useState<number>(0.7);
  const [maxTokens, setMaxTokens] = useState<number>(1000); // New state for max tokens
  const [personaSettings, setPersonaSettings] = useState<Record<string, { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }>>({}); // Per-persona settings

  const queryClient = useQueryClient();
  const { models: availableModels, defaultModel, getEffectiveModel, getModelLabel } = useLLMModels();

  const handlePersonaSettingsChange = (personaId: string, settings: { llm: string | null; temperature: number; maxTokens: number; prompt: string; description: string; name: string; icon: string }) => {
    setPersonaSettings(prev => ({ ...prev, [personaId]: settings }));
  };

  const handlePersonaSelect = async (personaId: string) => {
    const settings = personaSettings[personaId] || { llm: selectedLLM, temperature, maxTokens, prompt: '', description: '', name: '', icon: '' };
    const effectiveModel = getEffectiveModel(settings.llm);
    try {
      const newSession = await createChatSession({
        title: `Chat with ${personaId}`,
        started_by_persona: true,
        persona: parseInt(personaId),
        llm_id: effectiveModel || undefined,
        temperature: settings.temperature,
      });
      setSelectedSession(newSession.data.id.toString());
      setSelectedPersona(personaId);
      setSelectedTemplate(null);
      setTemplateVariables({});
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      toast({
        title: "Persona Selected",
        description: `Started chat with ${personaId}`,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to start persona chat",
        variant: "destructive",
      });
    }
  };

  const handleCreatePersona = () => {
    toast({
      title: "Create Persona",
      description: "Persona creation dialog would open here",
    });
  };

  const handleTemplateSelect = async (template: ChatbotTemplate) => {
    if (template.variables && template.variables.length > 0) {
      // If template has variables, show dialog
      setPendingTemplate({
        id: template.id.toString(),
        variables: template.variables.map(v => v.name),
        name: template.name,
        template: template,
      });
      setIsVariableDialogOpen(true);
    } else {
      // If no variables, apply template immediately and start chat
      const effectiveModel = getEffectiveModel(selectedLLM);
      try {
        const newSession = await createChatSession({
          title: `Chat with ${template.name} template`,
          started_by_persona: false,
          template: template.id,
          llm_id: effectiveModel || undefined,
          temperature: temperature
        });
        setSelectedSession(newSession.data.id.toString());
        setSelectedTemplate(template.id.toString());
        setTemplateVariables({});
        setSelectedPersona(null);
        queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
        toast({
          title: "Template Selected",
          description: `Using ${template.name} template`,
        });
      } catch (error) {
        toast({
          title: "Error",
          description: "Failed to start template chat",
          variant: "destructive",
        });
      }
    }
  };

  const handleVariableSubmit = async (variables: Record<string, string>) => {
    if (pendingTemplate) {
      const effectiveModel = getEffectiveModel(selectedLLM);
      try {
        const newSession = await createChatSession({
          title: `Chat with ${pendingTemplate.name} template`,
          started_by_persona: false,
          template: parseInt(pendingTemplate.id),
          llm_id: effectiveModel || undefined,
          temperature: temperature
        });
        
        // Apply template variables to the prompt
        const templatedMessage = applyTemplateVariables(pendingTemplate.template, variables);
        
        // Send the templated message as the first message
        if (templatedMessage.trim()) {
          await sendChatMessage(newSession.data.id, templatedMessage, effectiveModel || undefined, temperature);
        }
        
        setSelectedSession(newSession.data.id.toString());
        setSelectedTemplate(pendingTemplate.id);
        setTemplateVariables(variables);
        setSelectedPersona(null);
        queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
        
        toast({
          title: "Template Applied",
          description: `Starting chat with ${pendingTemplate.name} template`,
        });
        
        setPendingTemplate(null);
      } catch (error) {
        toast({
          title: "Error",
          description: "Failed to start template chat",
          variant: "destructive",
        });
      }
    }
  };

  const handleVariableDialogClose = () => {
    setIsVariableDialogOpen(false);
    setPendingTemplate(null);
  };

  const handleSessionSelect = (sessionId: string) => {
    setSelectedSession(sessionId);
    toast({
      title: "Chat Loaded",
      description: "Previous conversation loaded successfully",
    });
  };

  const handleDeleteSession = (sessionId: string) => {
    toast({
      title: "Chat Deleted",
      description: "Conversation removed from history",
      variant: "destructive",
    });
  };

  const handleNewChat = async () => {
    const effectiveModel = getEffectiveModel(selectedLLM);
    try {
      const newSession = await createChatSession({
        title: 'New Chat',
        started_by_persona: false,
        llm_id: effectiveModel || undefined,
        temperature: temperature
      });
      setSelectedSession(newSession.data.id.toString());
      setSelectedPersona(null);
      setSelectedTemplate(null);
      setTemplateVariables({});
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      toast({
        title: "New Chat",
        description: "Started a fresh conversation",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to create new chat session",
        variant: "destructive",
      });
    }
  };

  // Get template name and variable information for dialog
  const getTemplateInfo = () => {
    if (!pendingTemplate) return { name: '', variables: [] };
    
    return {
      name: pendingTemplate.name,
      variables: pendingTemplate.variables,
    };
  };

  const templateInfo = getTemplateInfo();

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="Enterprise Chatbot"
          description="Interact with AI using customizable personas and templates for enhanced productivity."
          icon={<MessageSquare size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        <div style={{ height: 'calc(100vh - 280px)' }}>
          <ResizablePanelGroup direction="horizontal" className="h-full w-full">
            {/* Left Sidebar - Personas & Templates */}
            <ResizablePanel defaultSize={25} minSize={20} maxSize={35}>
              <Card className="h-full m-0 rounded-none border-0">
                <CardBody style={{ padding: 0, height: '100%' }}>
                  <Tabs defaultValue="history" className="h-full flex flex-col">
                    <TabsList className="w-full grid grid-cols-3 rounded-none border-b">
                      <TabsTrigger value="history">History</TabsTrigger>
                      <TabsTrigger value="personas">Personas</TabsTrigger>
                      <TabsTrigger value="templates">Templates</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="history" className="flex-1 m-0 overflow-hidden">
                      <ChatHistory
                        selectedSession={selectedSession}
                        onSessionSelect={handleSessionSelect}
                        onDeleteSession={handleDeleteSession}
                        onNewChat={handleNewChat}
                        personasData={personasData.personas}
                      />
                    </TabsContent>
                    
                    <TabsContent value="personas" className="flex-1 m-0 overflow-hidden">
                      <PersonaSelector
                        selectedPersona={selectedPersona}
                        onPersonaSelect={handlePersonaSelect}
                        onCreatePersona={handleCreatePersona}
                        personasData={personasData.personas}
                        personaSettings={personaSettings}
                        onPersonaSettingsChange={handlePersonaSettingsChange}
                        availableModels={availableModels}
                        defaultModel={defaultModel}
                        getModelLabel={getModelLabel}
                      />
                    </TabsContent>
                    
                    <TabsContent value="templates" className="flex-1 m-0 overflow-hidden">
                      <TemplateManager
                        selectedTemplate={selectedTemplate}
                        onTemplateSelect={handleTemplateSelect}
                      />
                    </TabsContent>
                  </Tabs>
                </CardBody>
              </Card>
            </ResizablePanel>

            <ResizableHandle withHandle className="w-2 bg-border hover:bg-primary/20 transition-colors" />

            {/* Main Chat Area */}
            <ResizablePanel defaultSize={75} minSize={50}>
              <Card className="h-full m-0 rounded-none border-0">
                <CardBody style={{ padding: 0, height: '100%' }}>
                  <ChatInterface
                    selectedPersona={selectedPersona}
                    selectedTemplate={selectedTemplate}
                    templateVariables={templateVariables}
                    selectedSession={selectedSession}
                    selectedLLM={selectedLLM}
                    temperature={temperature}
                    maxTokens={maxTokens}
                    onPersonaChange={setSelectedPersona}
                    onTemplateChange={setSelectedTemplate}
                    onLLMChange={setSelectedLLM}
                    onTemperatureChange={setTemperature}
                    onMaxTokensChange={setMaxTokens}
                    isPersonaChat={!!selectedPersona}
                    availableModels={availableModels}
                    defaultModel={defaultModel}
                    getModelLabel={getModelLabel}
                  />
                </CardBody>
              </Card>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>

        {/* Template Variable Dialog */}
        <TemplateVariableDialog
          isOpen={isVariableDialogOpen}
          onClose={handleVariableDialogClose}
          onSubmit={handleVariableSubmit}
          templateName={templateInfo.name}
          variables={templateInfo.variables}
          descriptions={{}}
        />
      </PageSection>
    </Page>
  );
};

export default EnterpriseChatbot;
