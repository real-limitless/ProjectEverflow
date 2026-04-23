import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';
import pageContent from '@/data/pageContent.json';

const ApplicationPreview = () => {
  const { appName } = useParams();
  const navigate = useNavigate();

  return (
    <div className="flex flex-col h-screen bg-background">
      <div className="flex items-center gap-4 p-4 border-b border-border bg-card">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate('/my-applications')}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold">{appName}</h1>
          <p className="text-sm text-muted-foreground">{pageContent.applicationPreview.title}</p>
        </div>
      </div>
      
      <div className="flex-1 flex items-center justify-center bg-muted/20">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-semibold">{pageContent.applicationPreview.runningText} {appName}</h2>
          <p className="text-muted-foreground">{pageContent.applicationPreview.placeholderText}</p>
        </div>
      </div>
    </div>
  );
};

export default ApplicationPreview;
