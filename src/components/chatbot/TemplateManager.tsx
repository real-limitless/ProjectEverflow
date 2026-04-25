import { useState } from 'react';
import { Button } from '@patternfly/react-core';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Search, FileText, Plus, Edit2, Trash2, Loader2 } from 'lucide-react';
import { EditTemplateDialog } from './EditTemplateDialog';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getChatbotTemplates, createChatbotTemplate, updateChatbotTemplate, deleteChatbotTemplate, ChatbotTemplate } from '@/lib/api';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from '@/hooks/use-toast';

interface TemplateVariable {
  name: string;
  defaultValue: string;
  description: string;
}

interface Template {
  id: string;
  name: string;
  description: string;
  variables: TemplateVariable[];
  systemPrompt: string;
  userPromptTemplate: string;
}

interface TemplateManagerProps {
  selectedTemplate: string | null;
  onTemplateSelect: (template: ChatbotTemplate) => void;
}

export const TemplateManager: React.FC<TemplateManagerProps> = ({
  selectedTemplate,
  onTemplateSelect,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ChatbotTemplate | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [templateToDelete, setTemplateToDelete] = useState<number | null>(null);

  const queryClient = useQueryClient();

  const { data: templates, isLoading, error } = useQuery({
    queryKey: ['chatbot-templates'],
    queryFn: () => getChatbotTemplates(),
    select: (response) => response.data,
  });

  const createMutation = useMutation({
    mutationFn: createChatbotTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chatbot-templates'] });
      toast({
        title: 'Template Created',
        description: 'The template has been created successfully.',
      });
      setIsEditDialogOpen(false);
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to create template. Please try again.',
        variant: 'destructive',
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ChatbotTemplate> }) =>
      updateChatbotTemplate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chatbot-templates'] });
      toast({
        title: 'Template Updated',
        description: 'The template has been updated successfully.',
      });
      setIsEditDialogOpen(false);
      setEditingTemplate(null);
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to update template. Please try again.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteChatbotTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chatbot-templates'] });
      toast({
        title: 'Template Deleted',
        description: 'The template has been removed successfully.',
        variant: 'destructive',
      });
      setDeleteDialogOpen(false);
      setTemplateToDelete(null);
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to delete template. Please try again.',
        variant: 'destructive',
      });
    },
  });

  const filteredTemplates = templates?.filter(template =>
    template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    template.description.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const handleTemplateSelect = (templateId: string) => {
    const template = templates?.find(t => t.id.toString() === templateId);
    if (template) {
      onTemplateSelect(template);
    }
  };

  const handleCreateTemplate = () => {
    setEditingTemplate(null);
    setIsEditDialogOpen(true);
  };

  const handleEditTemplate = (template: ChatbotTemplate, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingTemplate(template);
    setIsEditDialogOpen(true);
  };

  const handleDeleteTemplate = (templateId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setTemplateToDelete(templateId);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (templateToDelete) {
      deleteMutation.mutate(templateToDelete);
    }
  };

  const handleSaveTemplate = (template: ChatbotTemplate) => {
    if (editingTemplate) {
      updateMutation.mutate({ id: editingTemplate.id, data: template });
    } else {
      createMutation.mutate({
        name: template.name,
        description: template.description,
        system_prompt: template.system_prompt,
        user_prompt_template: template.user_prompt_template,
        variables: template.variables,
        category: template.category,
        is_active: template.is_active,
      });
    }
  };

  if (error) {
    toast({
      title: "Error loading templates",
      description: "Failed to load chatbot templates. Please try again.",
      variant: "destructive",
    });
  }

  return (
    <>
      <div className="h-full flex flex-col">
        <div className="p-4 border-b space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Templates</h3>
            <Button variant="secondary" size="sm" onClick={handleCreateTemplate}>
              <Plus size={14} className="mr-1" />
              New
            </Button>
            
          </div>
          <div className="relative">        <p className="text-xs text-muted-foreground">
          Choose an AI persona for specialized assistance
        </p>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground"  />
            <Input
              placeholder="Search templates..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-4 space-y-3">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="ml-2 text-sm text-muted-foreground">Loading templates...</span>
              </div>
            ) : filteredTemplates.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                  {searchQuery ? 'No templates found' : 'No templates available'}
                </CardContent>
              </Card>
            ) : (
              filteredTemplates.map((template) => (
                <Card
                  key={template.id}
                  className={`cursor-pointer transition-all hover:shadow-md ${
                    selectedTemplate === template.id.toString()
                      ? 'border-primary bg-primary/5'
                      : 'hover:border-primary/50'
                  }`}
                  onClick={() => handleTemplateSelect(template.id.toString())}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-3 flex-1">
                        <div className="rounded-lg bg-primary/10 p-2 mt-1">
                          <FileText className="h-4 w-4 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-base line-clamp-1">
                            {template.name}
                          </CardTitle>
                          <CardDescription className="line-clamp-2 mt-1">
                            {template.description}
                          </CardDescription>
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          variant="plain"
                          size="sm"
                          onClick={(e) => handleEditTemplate(template, e)}
                          className="h-8 w-8 p-0"
                        >
                          <Edit2 className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="plain"
                          size="sm"
                          onClick={(e) => handleDeleteTemplate(template.id, e)}
                          className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  {template.variables.length > 0 && (
                    <CardContent className="pt-0">
                      <div className="flex flex-wrap gap-1">
                        {template.variables.map((variable) => (
                          <Badge key={variable.name} variant="secondary" className="text-xs">
                            {variable.name}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  )}
                </Card>
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      <EditTemplateDialog
        isOpen={isEditDialogOpen}
        onClose={() => setIsEditDialogOpen(false)}
        onSave={handleSaveTemplate}
        template={editingTemplate}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Template</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this template? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
