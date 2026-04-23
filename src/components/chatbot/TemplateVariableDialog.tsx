import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface TemplateVariable {
  name: string;
  description?: string;
}

interface TemplateVariableDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (variables: Record<string, string>) => void;
  templateName: string;
  variables: (string | TemplateVariable)[];
  descriptions?: Record<string, string>;
}

export const TemplateVariableDialog: React.FC<TemplateVariableDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  templateName,
  variables,
  descriptions = {},
}) => {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Normalize variables to handle both string and object formats
  const normalizedVariables = variables.map(v => {
    if (typeof v === 'string') {
      return { name: v, description: descriptions[v] };
    }
    return v as TemplateVariable;
  });

  useEffect(() => {
    // Initialize values when dialog opens
    if (isOpen) {
      const initialValues: Record<string, string> = {};
      normalizedVariables.forEach(variable => {
        initialValues[variable.name] = '';
      });
      setValues(initialValues);
      setErrors({});
    }
  }, [isOpen, variables]);

  const handleChange = (variableName: string, value: string) => {
    setValues(prev => ({ ...prev, [variableName]: value }));
    // Clear error when user starts typing
    if (errors[variableName]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[variableName];
        return newErrors;
      });
    }
  };

  const validate = () => {
    const newErrors: Record<string, string> = {};
    normalizedVariables.forEach(variable => {
      if (!values[variable.name]?.trim()) {
        newErrors[variable.name] = 'This field is required';
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = () => {
    if (validate()) {
      onSubmit(values);
      onClose();
    }
  };

  const handleCancel = () => {
    setValues({});
    setErrors({});
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleCancel}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Fill Template Variables</DialogTitle>
          <DialogDescription>
            Please provide values for the following variables in the "{templateName}" template.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {normalizedVariables.length === 0 ? (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                This template has no variables to fill.
              </AlertDescription>
            </Alert>
          ) : (
            normalizedVariables.map((variable) => {
              const variableName = variable.name;
              const description = variable.description || '';
              const variableLower = variableName.toLowerCase();
              const descriptionLower = description.toLowerCase();
              
              const isLongText = descriptionLower.includes('description') || 
                                 descriptionLower.includes('details') ||
                                 descriptionLower.includes('paragraph') ||
                                 descriptionLower.includes('content') ||
                                 variableLower.includes('description') ||
                                 variableLower.includes('details') ||
                                 variableLower.includes('content') ||
                                 variableLower.includes('body');

              return (
                <div key={variableName} className="space-y-2">
                  <Label htmlFor={variableName} className="text-base font-semibold">
                    {variableName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    <span className="text-destructive ml-1">*</span>
                  </Label>
                  {description && (
                    <p className="text-sm text-muted-foreground">
                      {description}
                    </p>
                  )}
                  {isLongText ? (
                    <Textarea
                      id={variableName}
                      value={values[variableName] || ''}
                      onChange={(e) => handleChange(variableName, e.target.value)}
                      placeholder={`Enter ${variableName.replace(/_/g, ' ')}`}
                      rows={4}
                      className={errors[variableName] ? 'border-destructive' : ''}
                      aria-label={variableName.replace(/_/g, ' ')}
                    />
                  ) : (
                    <Input
                      id={variableName}
                      value={values[variableName] || ''}
                      onChange={(e) => handleChange(variableName, e.target.value)}
                      placeholder={`Enter ${variableName.replace(/_/g, ' ')}`}
                      className={errors[variableName] ? 'border-destructive' : ''}
                      aria-label={variableName.replace(/_/g, ' ')}
                    />
                  )}
                  {errors[variableName] && (
                    <p className="text-sm text-destructive">{errors[variableName]}</p>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={handleCancel}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={normalizedVariables.length === 0}>
            Start Chat
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};