import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from '@/hooks/use-toast';
import { createWorkflow } from '@/lib/api';
import { Loader2, Plus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

interface CreateWorkflowDialogProps {
  projectId: number;
  projectName: string;
  trigger?: React.ReactNode;
}

const CreateWorkflowDialog: React.FC<CreateWorkflowDialogProps> = ({
  projectId,
  projectName,
  trigger
}) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
  });
  const queryClient = useQueryClient();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      toast({
        title: "Validation Error",
        description: "Workflow name is required.",
        variant: "destructive",
      });
      return;
    }

    try {
      setLoading(true);

      const workflowData = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        project: projectId,
        status: 'draft',
        nodes: [],
        edges: [],
        settings: {},
      };

      const response = await createWorkflow(workflowData);

      if (response.data) {
        toast({
          title: "Success",
          description: "Workflow created successfully!",
        });
        // Reset form
        setFormData({ name: '', description: '' });
        setOpen(false);
        // Invalidate workflows query to refresh the list
        queryClient.invalidateQueries({ queryKey: ['workflows'] });
      } else {
        toast({
          title: "Error",
          description: response.error || "Failed to create workflow.",
          variant: "destructive",
        });
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to create workflow.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const defaultTrigger = (
    <Button variant="default" size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Create Workflow
    </Button>
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || defaultTrigger}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create New Workflow</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Create an automated workflow for <strong>{projectName}</strong>
          </p>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="name" className="text-sm font-medium">
              Workflow Name *
            </Label>
            <Input
              id="name"
              type="text"
              placeholder="e.g., CI/CD Pipeline, Deployment Workflow"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className="mt-1"
              required
            />
          </div>

          <div>
            <Label htmlFor="description" className="text-sm font-medium">
              Description
            </Label>
            <Textarea
              id="description"
              placeholder="Describe what this workflow does..."
              value={formData.description}
              onChange={(e) => handleInputChange('description', e.target.value)}
              className="mt-1"
              rows={3}
            />
          </div>

          {/* Workflow Preview/Info */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <h4 className="text-sm font-medium text-blue-900 mb-2">What happens next?</h4>
            <ul className="text-xs text-blue-800 space-y-1">
              <li>• Your workflow will be created in draft status</li>
              <li>• You'll be able to design the workflow steps and connections</li>
              <li>• Set up triggers, actions, and conditions for automation</li>
              <li>• Test and activate the workflow when ready</li>
            </ul>
          </div>

          {/* Actions */}
          <div className="flex justify-end space-x-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={loading || !formData.name.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                'Create Workflow'
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateWorkflowDialog;