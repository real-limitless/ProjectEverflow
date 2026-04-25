import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@patternfly/react-core';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Plus, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { ChatbotTemplate } from '@/lib/api';

interface TemplateVariable {
  name: string;
  defaultValue: string;
  description: string;
}

interface TemplateFormData {
  id: string;
  name: string;
  description: string;
  variables: TemplateVariable[];
  systemPrompt: string;
  userPromptTemplate: string;
  category: string;
  is_active: boolean;
}

interface EditTemplateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (template: ChatbotTemplate) => void;
  template: ChatbotTemplate | null;
}

export const EditTemplateDialog: React.FC<EditTemplateDialogProps> = ({
  isOpen,
  onClose,
  onSave,
  template,
}) => {
  const [formData, setFormData] = useState<TemplateFormData>({
    id: '',
    name: '',
    description: '',
    variables: [],
    systemPrompt: '',
    userPromptTemplate: '',
    category: 'general',
    is_active: true,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (template) {
      // Convert API data to form data
      setFormData({
        id: template.id.toString(),
        name: template.name,
        description: template.description,
        variables: template.variables,
        systemPrompt: template.system_prompt,
        userPromptTemplate: template.user_prompt_template,
        category: template.category,
        is_active: template.is_active,
      });
    } else {
      setFormData({
        id: `template-${Date.now()}`,
        name: '',
        description: '',
        variables: [],
        systemPrompt: '',
        userPromptTemplate: '',
        category: 'general',
        is_active: true,
      });
    }
    setErrors({});
  }, [template, isOpen]);

  const handleChange = (field: keyof TemplateFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  const handleVariableChange = (index: number, field: keyof TemplateVariable, value: string) => {
    setFormData(prev => ({
      ...prev,
      variables: prev.variables.map((v, i) => 
        i === index ? { ...v, [field]: value } : v
      ),
    }));
  };

  const addVariable = () => {
    setFormData(prev => ({
      ...prev,
      variables: [
        ...prev.variables,
        { name: '', defaultValue: '', description: '' },
      ],
    }));
  };

  const removeVariable = (index: number) => {
    setFormData(prev => ({
      ...prev,
      variables: prev.variables.filter((_, i) => i !== index),
    }));
  };

  const validate = () => {
    const newErrors: Record<string, string> = {};
    
    if (!formData.name.trim()) {
      newErrors.name = 'Template name is required';
    }
    if (!formData.description.trim()) {
      newErrors.description = 'Description is required';
    }
    if (!formData.systemPrompt.trim()) {
      newErrors.systemPrompt = 'System prompt is required';
    }
    if (!formData.userPromptTemplate.trim()) {
      newErrors.userPromptTemplate = 'User prompt template is required';
    }

    formData.variables.forEach((variable, index) => {
      if (!variable.name.trim()) {
        newErrors[`variable_${index}_name`] = 'Variable name is required';
      }
      if (!variable.description.trim()) {
        newErrors[`variable_${index}_description`] = 'Variable description is required';
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = () => {
    if (validate()) {
      // Convert form data to API format
      const apiTemplate: ChatbotTemplate = {
        id: template ? template.id : 0, // Will be set by backend for new templates
        name: formData.name,
        description: formData.description,
        system_prompt: formData.systemPrompt,
        user_prompt_template: formData.userPromptTemplate,
        variables: formData.variables,
        category: formData.category,
        is_active: formData.is_active,
        created_at: template?.created_at || '',
        updated_at: template?.updated_at || '',
      };
      onSave(apiTemplate);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{template ? 'Edit Template' : 'Create New Template'}</DialogTitle>
          <DialogDescription>
            {template ? 'Update the template details below.' : 'Create a new chatbot template with custom variables.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Basic Information */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Template Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="e.g., Email Writer"
                className={errors.name ? 'border-destructive' : ''}
              />
              {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description *</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Brief description of what this template does"
                className={errors.description ? 'border-destructive' : ''}
              />
              {errors.description && <p className="text-sm text-destructive">{errors.description}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <Input
                id="category"
                value={formData.category}
                onChange={(e) => handleChange('category', e.target.value)}
                placeholder="e.g., general, coding, writing"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="systemPrompt">System Prompt *</Label>
              <Textarea
                id="systemPrompt"
                value={formData.systemPrompt}
                onChange={(e) => handleChange('systemPrompt', e.target.value)}
                placeholder="Define the AI's role and behavior"
                rows={3}
                className={errors.systemPrompt ? 'border-destructive' : ''}
              />
              {errors.systemPrompt && <p className="text-sm text-destructive">{errors.systemPrompt}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="userPromptTemplate">User Prompt Template *</Label>
              <Textarea
                id="userPromptTemplate"
                value={formData.userPromptTemplate}
                onChange={(e) => handleChange('userPromptTemplate', e.target.value)}
                placeholder="Template with variables like {{variable_name}}"
                rows={3}
                className={errors.userPromptTemplate ? 'border-destructive' : ''}
              />
              {errors.userPromptTemplate && <p className="text-sm text-destructive">{errors.userPromptTemplate}</p>}
              <p className="text-xs text-muted-foreground">
                Use {`{{variable_name}}`} syntax to include variables
              </p>
            </div>
          </div>

          {/* Variables Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-base">Template Variables</Label>
              <Button onClick={addVariable} size="sm" variant="secondary">
                <Plus size={14} className="mr-1" />
                Add Variable
              </Button>
            </div>

            {formData.variables.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                  No variables added yet. Click "Add Variable" to create one.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {formData.variables.map((variable, index) => (
                  <Card key={index}>
                    <CardContent className="pt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <Label className="font-semibold">Variable {index + 1}</Label>
                        <Button
                          onClick={() => removeVariable(index)}
                          size="sm"
                          variant="plain"
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor={`variable_${index}_name`}>Variable Name *</Label>
                        <Input
                          id={`variable_${index}_name`}
                          value={variable.name}
                          onChange={(e) => handleVariableChange(index, 'name', e.target.value)}
                          placeholder="e.g., recipient"
                          className={errors[`variable_${index}_name`] ? 'border-destructive' : ''}
                        />
                        {errors[`variable_${index}_name`] && (
                          <p className="text-sm text-destructive">{errors[`variable_${index}_name`]}</p>
                        )}
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor={`variable_${index}_defaultValue`}>Default Value</Label>
                        <Input
                          id={`variable_${index}_defaultValue`}
                          value={variable.defaultValue}
                          onChange={(e) => handleVariableChange(index, 'defaultValue', e.target.value)}
                          placeholder="Optional default value"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor={`variable_${index}_description`}>Description *</Label>
                        <Textarea
                          id={`variable_${index}_description`}
                          value={variable.description}
                          onChange={(e) => handleVariableChange(index, 'description', e.target.value)}
                          placeholder="Explain what this variable is for"
                          rows={2}
                          className={errors[`variable_${index}_description`] ? 'border-destructive' : ''}
                        />
                        {errors[`variable_${index}_description`] && (
                          <p className="text-sm text-destructive">{errors[`variable_${index}_description`]}</p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit}>
            {template ? 'Save Changes' : 'Create Template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};