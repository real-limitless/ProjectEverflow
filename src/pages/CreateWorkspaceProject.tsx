import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useNavigate } from 'react-router-dom';
import { GitBranch, MessageSquare, FileText, Sparkles, FolderOpen } from 'lucide-react';
import { ProjectCreationWizard } from '@/components/project/ProjectCreationWizard';
import { ArrowLeftIcon } from '@patternfly/react-icons';

type CreationMethod = "blank" | "clone" | "chat" | "template" | null;

const CreateWorkspaceProject = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const navigate = useNavigate();
  const [selectedMethod, setSelectedMethod] = useState<CreationMethod>(null);

  const creationOptions = [
    {
      id: "blank" as const,
      title: "Start from Scratch",
      description: "Create a blank project with basic structure",
      icon: FileText,
      color: "text-blue-500",
      bgColor: "bg-blue-50 dark:bg-blue-950",
    },
    {
      id: "clone" as const,
      title: "Clone Existing Repository",
      description: "Import code from GitHub, GitLab, or other Git repositories",
      icon: GitBranch,
      color: "text-purple-500",
      bgColor: "bg-purple-50 dark:bg-purple-950",
    },
    {
      id: "chat" as const,
      title: "AI-Assisted Planning",
      description: "Chat with AI to generate project architecture and AGENTS.md documentation",
      icon: MessageSquare,
      color: "text-green-500",
      bgColor: "bg-green-50 dark:bg-green-950",
    },
    {
      id: "template" as const,
      title: "Use Template",
      description: "Start from pre-built templates (React, Django, FastAPI, etc.)",
      icon: Sparkles,
      color: "text-orange-500",
      bgColor: "bg-orange-50 dark:bg-orange-950",
    },
  ];

  const renderSelectionCards = () => (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-6xl mx-auto">
      {creationOptions.map((option) => {
        const Icon = option.icon;
        return (
          <Card
            key={option.id}
            className="cursor-pointer hover:shadow-lg transition-all duration-200 hover:scale-105"
            onClick={() => setSelectedMethod(option.id)}
            style={{ border: '1px solid var(--pf-v6-global--BorderColor--100)' }}
          >
            <CardBody>
              <div className="flex flex-col items-center text-center space-y-4">
                <div className={`w-16 h-16 rounded-lg ${option.bgColor} flex items-center justify-center`}>
                  <Icon className={`h-8 w-8 ${option.color}`} />
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">{option.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">
                    {option.description}
                  </p>
                </div>
                <Button variant="secondary" className="mt-4">
                  Select
                </Button>
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );

  const renderWizard = () => (
    <div className="max-w-6xl mx-auto">

      <ProjectCreationWizard
        method={selectedMethod!}
        onCancel={() => navigate("/my-teamspace")}
        onComplete={() => navigate("/my-teamspace")}
      />
    </div>
  );

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <FolderOpen size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />
              Create New Team Project
            </h1>
            <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
              Choose how you'd like to start your new AI application project
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>

          </div>
        </div>

        {selectedMethod ? renderWizard() : renderSelectionCards()}

        {!selectedMethod && (
          <div className="text-center mt-8">
            <Button variant="secondary" onClick={() => navigate("/my-teamspace")}>
              Cancel
            </Button>
          </div>
        )}
      </PageSection>
    </Page>
  );
};

export default CreateWorkspaceProject;
