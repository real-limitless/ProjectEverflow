import { BlankProjectForm } from "./creation/BlankProjectForm";
import { CloneRepositoryForm } from "./creation/CloneRepositoryForm";
import { AIPlanningChat } from "./creation/AIPlanningChat";
import { TemplateSelector } from "./creation/TemplateSelector";

interface ProjectCreationWizardProps {
  method: "blank" | "clone" | "chat" | "template";
  onCancel: () => void;
  onComplete: () => void;
}

export function ProjectCreationWizard({ method, onCancel, onComplete }: ProjectCreationWizardProps) {
  const renderMethodContent = () => {
    switch (method) {
      case "blank":
        return <BlankProjectForm onCancel={onCancel} onComplete={onComplete} />;
      case "clone":
        return <CloneRepositoryForm onCancel={onCancel} onComplete={onComplete} />;
      case "chat":
        return <AIPlanningChat onCancel={onCancel} onComplete={onComplete} />;
      case "template":
        return <TemplateSelector onCancel={onCancel} onComplete={onComplete} />;
      default:
        return null;
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      {renderMethodContent()}
    </div>
  );
}