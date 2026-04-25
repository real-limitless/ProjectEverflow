import { useState } from "react";
import { Card, CardBody, CardTitle, Button as PatternFlyButton, TextInput, Badge } from '@patternfly/react-core';
import { useToast } from "@/hooks/use-toast";
import { Search, Sparkles } from "lucide-react";
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { createProject, getCurrentUser, getProjectTemplates, ProjectTemplate } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';

interface TemplateSelectorProps {
  onCancel: () => void;
  onComplete: () => void;
}

export function TemplateSelector({ onCancel, onComplete }: TemplateSelectorProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Fetch templates from API
  const { data: templates, isLoading, error } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => getProjectTemplates(),
    select: (response) => response.data || [],
  });

  const filteredTemplates = (templates || []).filter(
    (template) =>
      template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      template.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      template.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const handleCreate = async () => {
    if (!selectedTemplate) return;

    setIsCreating(true);
    const template = templates?.find((t) => t.id.toString() === selectedTemplate);

    try {
      // Get current user for owner field
      const userResponse = await getCurrentUser();
      if (userResponse.error) {
        toast({
          title: "Authentication Error",
          description: "Please log in to create a project.",
          variant: "destructive",
        });
        setIsCreating(false);
        return;
      }

      const response = await createProject({
        name: template?.name || "Template Project",
        description: template?.description || "Project created from template.",
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
          description: `${template?.name} has been created successfully.`,
        });
        onComplete();
      }
    } catch (error) {
      toast({
        title: "Error Creating Project",
        description: "An unexpected error occurred while creating the project.",
        variant: "destructive",
      });
    } finally {
      setIsCreating(false);
    }
  };

  const getDifficultyColor = (difficulty: ProjectTemplate["difficulty"]) => {
    switch (difficulty) {
      case "beginner":
        return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
      case "intermediate":
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
      case "advanced":
        return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    }
  };

  return (
    <div>

      
      <div className="space-y-6">
        <Card style={{ maxWidth: '1000px' }}>
          <CardBody>
            <CardTitle>Choose a Template</CardTitle>
            <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
              Start from a pre-built template with best practices and common patterns
            </p>

            <div className="relative mb-6">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <TextInput
                placeholder="Search templates..."
                value={searchQuery}
                onChange={(_event, value) => setSearchQuery(value)}
                className="pl-10"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredTemplates.map((template) => (
                <Card
                  key={template.id}
                  className={`cursor-pointer transition-all hover:shadow-md ${
                    selectedTemplate === template.id.toString()
                      ? "ring-2 ring-primary"
                      : ""
                  }`}
                  onClick={() => setSelectedTemplate(template.id.toString())}
                  style={{ border: '1px solid var(--pf-v6-global--BorderColor--100)' }}
                >
                  <CardBody>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-primary" />
                        <h3 className="text-lg font-semibold">{template.name}</h3>
                      </div>
                      <Badge className={getDifficultyColor(template.difficulty)}>
                        {template.difficulty.charAt(0).toUpperCase() + template.difficulty.slice(1)}
                      </Badge>
                    </div>

                    <p className="text-sm text-muted-foreground mb-4">
                      {template.description}
                    </p>

                    <div className="space-y-3">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">Language:</span>
                        <Badge variant="secondary">{template.language}</Badge>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">Framework:</span>
                        <Badge variant="secondary">{template.framework}</Badge>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {template.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>

            {isLoading && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Loading templates...</p>
              </div>
            )}

            {error && (
              <div className="text-center py-12">
                <p className="text-destructive">Error loading templates. Please try again.</p>
              </div>
            )}

            {!isLoading && !error && filteredTemplates.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No templates found matching your search</p>
              </div>
            )}

            <div style={{ display: 'flex', gap: '1rem', paddingTop: '1rem' }}>
              <PatternFlyButton type="button" variant="primary" onClick={handleCreate} isDisabled={!selectedTemplate || isCreating}>
                {isCreating ? "Creating..." : "Create from Template"}
              </PatternFlyButton>
              <PatternFlyButton variant="secondary" onClick={onCancel} isDisabled={isCreating}>
                Cancel
              </PatternFlyButton>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}