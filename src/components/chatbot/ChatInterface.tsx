import { useState, useRef, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Button, Card, CardBody } from '@patternfly/react-core';
import { ScrollArea } from '@/components/ui/scroll-area';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Send, Loader2, Bot, User, Settings, ChevronDown } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getChatMessages, sendChatMessage, createChatSession, ChatMessage, summarizeConversation, updateChatSession, getChatbotPersonas, getChatbotTemplates, getAvailableLLMs, LLMConfig } from '@/lib/api';
import { LLMModelOption } from '@/hooks/use-llm-models';
import { toast } from '@/hooks/use-toast';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Tabs as UITabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface ChatInterfaceProps {
  selectedPersona: string | null;
  selectedTemplate: string | null;
  templateVariables?: Record<string, string>;
  selectedSession?: string | null;
  selectedLLM?: string | null;
  temperature?: number;
  maxTokens?: number;
  onPersonaChange?: (personaId: string | null) => void;
  onTemplateChange?: (templateId: string | null) => void;
  onLLMChange?: (llm: string) => void;
  onTemperatureChange?: (temperature: number) => void;
  onMaxTokensChange?: (maxTokens: number) => void;
  isPersonaChat?: boolean;
  availableModels?: LLMModelOption[];
  defaultModel?: string | null;
  getModelLabel?: (modelId: string | null) => string;
}

// Helper function to apply template variables
const applyTemplate = (template: any, variables: Record<string, string>): string => {
  if (!template) return '';
  
  let message = template.user_prompt_template || '';
  Object.entries(variables).forEach(([key, value]) => {
    message = message.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
  });
  return message;
};

export const ChatInterface = ({ 
  selectedPersona, 
  selectedTemplate, 
  templateVariables,
  selectedSession,
  selectedLLM,
  temperature = 0.7,
  maxTokens = 1000,
  onPersonaChange,
  onTemplateChange,
  onLLMChange,
  onTemperatureChange,
  onMaxTokensChange,
  isPersonaChat = false,
  availableModels = [],
  defaultModel = null,
  getModelLabel = (modelId) => modelId || 'Use Default Model',
}: ChatInterfaceProps) => {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const [initialMessages, setInitialMessages] = useState<Message[]>([]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  // Load messages for the selected session
  const { data: messages, isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', currentSessionId],
    queryFn: () => currentSessionId ? getChatMessages(currentSessionId) : Promise.resolve({ data: [] }),
    select: (response) => response.data || [],
    enabled: !!currentSessionId,
  });

  // Load available personas and templates for switching
  const { data: availablePersonas } = useQuery({
    queryKey: ['chatbot-personas'],
    queryFn: () => getChatbotPersonas(),
    select: (response) => response.data,
  });

  const { data: availableTemplates } = useQuery({
    queryKey: ['chatbot-templates'],
    queryFn: () => getChatbotTemplates(),
    select: (response) => response.data,
  });

  // Load available LLMs for the settings dropdown
  const { data: availableLLMs } = useQuery({
    queryKey: ['available-llms'],
    queryFn: () => getAvailableLLMs(),
    select: (response) => response.data,
  });

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (response) => {
      setCurrentSessionId(response.data.id);
      toast({
        title: 'Chat started',
        description: 'New conversation session created.',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to start chat session.',
        variant: 'destructive',
      });
    },
  });

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: number; message: string }) => sendChatMessage(sessionId, message, selectedLLM || undefined, temperature),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      setIsLoading(false);
      
      // Trigger summarization after message
      if (currentSessionId) {
        try {
          await summarizeConversation(currentSessionId);
          queryClient.invalidateQueries({ queryKey: ['chat-sessions'] }); // Update subject in history
        } catch (error) {
          console.error('Failed to summarize conversation:', error);
        }
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to send message.',
        variant: 'destructive',
      });
      setIsLoading(false);
    },
  });

  // Update session mutation for changing persona/template
  const updateSessionMutation = useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: number; data: Partial<any> }) => updateChatSession(sessionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      toast({
        title: 'Session updated',
        description: 'Persona or template changed successfully.',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to update session.',
        variant: 'destructive',
      });
    },
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Handle changing persona during conversation
  const handleChangePersona = (personaId: string) => {
    if (!currentSessionId) return;
    
    const persona = availablePersonas?.find(p => p.id.toString() === personaId);
    if (persona) {
      updateSessionMutation.mutate({
        sessionId: currentSessionId,
        data: { 
          persona: parseInt(personaId),
          template: null, // Clear template when switching to persona
          started_by_persona: true
        }
      });
      onPersonaChange?.(personaId);
      onTemplateChange?.(null);
    }
  };

  // Handle changing template during conversation
  const handleChangeTemplate = (templateId: string) => {
    if (!currentSessionId) return;
    
    const template = availableTemplates?.find(t => t.id.toString() === templateId);
    if (template) {
      updateSessionMutation.mutate({
        sessionId: currentSessionId,
        data: { 
          template: parseInt(templateId),
          persona: null, // Clear persona when switching to template
          started_by_persona: false
        }
      });
      onTemplateChange?.(templateId);
      onPersonaChange?.(null);
    }
  };

  // Handle session selection
  useEffect(() => {
    if (selectedSession) {
      const sessionId = parseInt(selectedSession);
      if (!isNaN(sessionId)) {
        setCurrentSessionId(sessionId);
      }
    } else {
      setCurrentSessionId(null);
    }
  }, [selectedSession]);

  // Handle initial persona/template messages
  useEffect(() => {
    if (selectedPersona && isPersonaChat) {
      const persona = availablePersonas?.find(p => p.id.toString() === selectedPersona);
      if (persona) {
        const greeting: Message = {
          role: 'assistant',
          content: `Hello! I'm ${persona.name}, ${persona.description}. How can I assist you today?`,
          timestamp: new Date()
        };
        setInitialMessages([greeting]);
      }
    } else {
      setInitialMessages([]);
    }
  }, [selectedPersona, isPersonaChat, availablePersonas]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    // Create session if none exists
    if (!currentSessionId) {
      createSessionMutation.mutate({
        title: `Chat Session ${new Date().toLocaleDateString()}`,
        persona: selectedPersona ? parseInt(selectedPersona) : undefined,
        template: selectedTemplate ? parseInt(selectedTemplate) : undefined,
        llm_id: selectedLLM || undefined,
        temperature: temperature,
      });
      return;
    }

    const userMessage = input;
    setInput('');
    setIsLoading(true);

    // Send user message and get AI response
    sendMessageMutation.mutate({
      sessionId: currentSessionId,
      message: userMessage,
    });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const displayMessages = messages && messages.length > 0 ? messages : initialMessages;

  return (
    <div className="flex flex-col h-full">
      {/* Chat Header with Persona/Template Controls */}
      {currentSessionId && (
        <div className="border-b p-3 flex items-center justify-between bg-muted/30">
          <div className="flex items-center gap-2">
            <Bot size={16} className="text-muted-foreground" />
            <span className="text-sm font-medium">Chat Session</span>
          </div>
          
          <Dialog open={isSettingsOpen} onOpenChange={setIsSettingsOpen}>
            <DialogTrigger asChild>
              <Button variant="plain" className="h-8 w-8 p-0">
                <Settings size={16} />
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>AI Chat Settings</DialogTitle>
                <DialogDescription>
                  Configure AI model parameters for this chat session
                </DialogDescription>
              </DialogHeader>
              
              <UITabs defaultValue="model" className="w-full">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="model">AI Model</TabsTrigger>
                  <TabsTrigger value="advanced">Advanced Settings</TabsTrigger>
                </TabsList>
                
                <TabsContent value="model" className="space-y-4 mt-4">
                  <div>
                    <Label>AI Model</Label>
                    <Select value={selectedLLM || ''} onValueChange={(value) => onLLMChange?.(value)}>
                      <SelectTrigger className="mt-2">
                        <SelectValue placeholder={defaultModel ? getModelLabel(null) : "Select AI model"} />
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
                          <>
                            <SelectItem value="google/gemini-2.5-flash">Google Gemini 2.5 Flash</SelectItem>
                            <SelectItem value="gpt-4">GPT-4</SelectItem>
                            <SelectItem value="gpt-3.5-turbo">GPT-3.5 Turbo</SelectItem>
                            <SelectItem value="claude-3-opus">Claude 3 Opus</SelectItem>
                            <SelectItem value="claude-3-sonnet">Claude 3 Sonnet</SelectItem>
                          </>
                        )}
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <div className="flex justify-between mb-2">
                      <Label>Temperature: {temperature}</Label>
                    </div>
                    <Slider
                      value={[temperature]}
                      onValueChange={(value) => onTemperatureChange?.(value[0])}
                      min={0}
                      max={2}
                      step={0.1}
                      className="mt-2"
                    />
                  </div>
                  
                  <div>
                    <div className="flex justify-between mb-2">
                      <Label>Max Tokens: {maxTokens}</Label>
                    </div>
                    <Slider
                      value={[maxTokens]}
                      onValueChange={(value) => onMaxTokensChange?.(value[0])}
                      min={100}
                      max={4000}
                      step={100}
                      className="mt-2"
                    />
                  </div>
                </TabsContent>
                
                <TabsContent value="advanced" className="space-y-4 mt-4">
                  <p className="text-sm text-muted-foreground">Advanced settings coming soon...</p>
                </TabsContent>
              </UITabs>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {/* Chat Messages */}
      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {messagesLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2 text-sm text-muted-foreground">Loading messages...</span>
            </div>
          ) : displayMessages.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Bot size={48} className="mx-auto mb-4 opacity-50" />
              <p className="text-sm">Start a conversation</p>
              <p className="text-xs mt-1">Send a message to begin chatting</p>
            </div>
          ) : (
            displayMessages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${
                  message.message_type === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {message.message_type === 'assistant' && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Bot size={16} className="text-primary" />
                  </div>
                )}
                <Card
                  className={`max-w-[70%] ${
                    message.message_type === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                  }`}
                >
                  <CardBody className="p-3">
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                    <p className="text-xs opacity-70 mt-1">
                      {new Date(message.created_at).toLocaleTimeString()}
                    </p>
                  </CardBody>
                </Card>
                {message.message_type === 'user' && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                    <User size={16} className="text-secondary-foreground" />
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t p-4">
        <div className="flex gap-2">
          <Input
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
            className="flex-1"
          />
          <Button
            onClick={handleSend}
            isDisabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        {selectedPersona && (
          <p className="text-xs text-muted-foreground mt-2">
            Chatting with persona: {selectedPersona}
          </p>
        )}
      </div>
    </div>
  );
};
