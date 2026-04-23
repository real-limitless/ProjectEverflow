import { useState, useRef, useEffect } from "react";
import { Card, CardBody, CardTitle, Button as PatternFlyButton } from '@patternfly/react-core';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from "@/hooks/use-toast";
import { Bot, User, Send, FileText, Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { createProject, getCurrentUser } from '@/lib/api';

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface AIPlanningChatProps {
  onCancel: () => void;
  onComplete: () => void;
}

export function AIPlanningChat({ onCancel, onComplete }: AIPlanningChatProps) {
  const { toast } = useToast();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "Hello! I'm here to help you plan your AI application project. I'll guide you through creating a comprehensive project architecture document and AGENTS.md file. Let's start with a few questions:\n\n1. What type of AI application are you building?\n2. What problem does it solve?\n3. Who are your target users?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [generatedDocs, setGeneratedDocs] = useState<{ agentsMd: string; architecture: string } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsTyping(true);

    // Simulate AI response
    setTimeout(() => {
      const responses = [
        "Great! That sounds like an interesting project. Can you tell me more about the key features you want to include?",
        "I understand. What technologies or frameworks are you planning to use?",
        "Perfect! Let me generate a comprehensive AGENTS.md and architecture document for you based on our discussion...",
      ];

      const response = responses[messages.filter((m) => m.role === "user").length % responses.length];

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response,
          timestamp: new Date(),
        },
      ]);
      setIsTyping(false);

      // Generate documents after a few exchanges
      if (messages.filter((m) => m.role === "user").length >= 3) {
        setTimeout(() => {
          setGeneratedDocs({
            agentsMd: "# Project Documentation\n\n## Overview\n\nThis is your AI application...",
            architecture: "# Architecture\n\n## System Design\n\n...",
          });
        }, 1000);
      }
    }, 1500);
  };

  const handleCreateProject = async () => {
    try {
      // Get current user for owner field
      const userResponse = await getCurrentUser();
      if (userResponse.error) {
        toast({
          title: "Authentication Error",
          description: "Please log in to create a project.",
          variant: "destructive",
        });
        return;
      }

      const response = await createProject({
        name: "AI-Planned Project", // Default name, could be made configurable
        description: "Project created with AI assistance and generated documentation.",
        owner: userResponse.data.id,
      });

      if (response.error) {
        toast({
          title: "Error Creating Project",
          description: response.error,
          variant: "destructive",
        });
      } else {
        toast({
          title: "Project Created",
          description: "Your project has been created with AI-generated documentation.",
        });
        onComplete();
      }
    } catch (error) {
      toast({
        title: "Error Creating Project",
        description: "An unexpected error occurred while creating the project.",
        variant: "destructive",
      });
    }
  };

  return (
    <div>
      <PatternFlyButton 
        variant="link" 
        icon={<ArrowLeftIcon />}
        onClick={onCancel}
        style={{ padding: 0, marginBottom: '1rem' }}
      >
        Back to Options
      </PatternFlyButton>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardBody>
          <CardTitle>AI Planning Assistant</CardTitle>
          <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
            Chat with AI to generate project architecture and documentation
          </p>

          <ScrollArea className="h-[500px] pr-4" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
                >
                  {message.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                      <Bot className="h-4 w-4 text-primary-foreground" />
                    </div>
                  )}
                  <div
                    className={`max-w-[80%] rounded-lg p-3 ${
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted"
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                    <p className="text-xs opacity-70 mt-1">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                  {message.role === "user" && (
                    <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              ))}
              {isTyping && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                    <Bot className="h-4 w-4 text-primary-foreground" />
                  </div>
                  <div className="bg-muted rounded-lg p-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce delay-100" />
                      <div className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce delay-200" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="flex gap-2 mt-4">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Type your message... (Press Enter to send)"
              rows={2}
            />
              <PatternFlyButton onClick={handleSend} variant="primary" className="flex-shrink-0">
                <Send className="h-4 w-4" />
              </PatternFlyButton>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <CardTitle className="text-lg">Generated Documents</CardTitle>
          <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
            AI-created documentation will appear here
          </p>

          {generatedDocs ? (
            <>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    <span className="text-sm font-medium">AGENTS.md</span>
                  </div>
                  <PatternFlyButton variant="secondary">
                    <Download className="h-4 w-4" />
                  </PatternFlyButton>
                </div>
                <Badge variant="secondary">Generated</Badge>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    <span className="text-sm font-medium">Architecture.md</span>
                  </div>
                  <PatternFlyButton variant="secondary">
                    <Download className="h-4 w-4" />
                  </PatternFlyButton>
                </div>
                <Badge variant="secondary">Generated</Badge>
              </div>

                <div className="pt-4 space-y-2">
                  <PatternFlyButton onClick={handleCreateProject} className="w-full">
                    Create Project with Docs
                  </PatternFlyButton>
                  <PatternFlyButton variant="secondary" onClick={onCancel} className="w-full">
                    Cancel
                  </PatternFlyButton>
                </div>
            </>
          ) : (
            <div className="text-center text-sm text-muted-foreground py-8">
              Continue chatting to generate documentation
            </div>
          )}
        </CardBody>
      </Card>
    </div>
    </div>
  );
}