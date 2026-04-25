## Development Guidelines

### Code Style
- Use TypeScript for type safety
- Functional components with hooks
- Follow Airbnb React style guide
- Use semantic HTML elements

### Component Structure
```typescript
// Component file structure
import React from 'react';
import { Button } from '@/components/ui/button';

interface ComponentProps {
  // Props interface
}

export const Component: React.FC<ComponentProps> = ({ ...props }) => {
  // Hooks at top
  // Event handlers
  // Render logic
  
  return (
    // JSX
  );
};
```

### Styling Guidelines
- Use Tailwind utility classes
- Reference semantic tokens from design system
- Avoid hardcoded colors (use HSL variables)
- Support light/dark modes
- Responsive design (mobile-first)
- **Z-Index Hierarchy**: Maintain consistent z-index values across UI components:
  - Base content: `z-0` to `z-10`
  - Dropdowns/menus: `z-50` to `z-60`
  - Tooltips: `z-70` to `z-80`
  - Dialog overlays: `z-[9999]`
  - Dialog content: `z-[10000]`
  - **Toast notifications: `z-[10001]` or higher** - Toasts must appear above all other UI elements including modals and dialogs

### Testing
- Unit tests for utility functions
- Component tests with React Testing Library
- E2E tests with Playwright/Cypress
- Test approval workflows thoroughly

### API Integration
- **Backend-First Development**: All new features that involve data persistence, user management, or business logic MUST be implemented on the backend API first
- **Real API Calls**: Frontend components should use actual API calls (not simulations) for all CRUD operations
- **Error Handling**: Implement proper error handling for API failures with user-friendly error messages
- **Loading States**: Show appropriate loading indicators during API operations
- **Data Validation**: Validate data on both frontend (user experience) and backend (security/data integrity)
- **Authentication**: Ensure all API calls include proper authentication headers
- **API Documentation**: Update API documentation when adding new endpoints or modifying existing ones

### Modal Implementation
Use the shadcn/ui Dialog components for consistent modal dialogs throughout the application. Follow this pattern for creating modals:

#### Basic Modal Structure
```typescript
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useState } from 'react';

export const MyComponent = () => {
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  return (
    <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
      <DialogTrigger asChild>
        <Button>Open Modal</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Modal Title</DialogTitle>
          <DialogDescription>
            Modal description explaining the purpose.
          </DialogDescription>
        </DialogHeader>
        {/* Modal content goes here */}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={() => setIsDialogOpen(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit}>
            Confirm
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

#### Modal with Form (IssuesTab.tsx Pattern)
For modals containing forms (like creating issues, projects, etc.), follow this structure:

```typescript
import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from '@/hooks/use-toast';

interface FormData {
  title: string;
  description: string;
  category: string;
  // Add other fields as needed
}

export const CreateModal = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState<FormData>({
    title: '',
    description: '',
    category: 'default'
  });

  const handleSubmit = async () => {
    // Validate required fields
    if (!formData.title.trim()) {
      toast({
        title: "Error",
        description: "Please enter a title.",
        variant: "destructive",
      });
      return;
    }

    try {
      // API call to create item
      // const response = await createItem(formData);
      
      toast({
        title: "Success",
        description: "Item created successfully.",
      });
      
      // Reset form and close modal
      setFormData({ title: '', description: '', category: 'default' });
      setIsOpen(false);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to create item.",
        variant: "destructive",
      });
    }
  };

  const handleCancel = () => {
    setFormData({ title: '', description: '', category: 'default' });
    setIsOpen(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">Create New Item</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create New Item</DialogTitle>
          <DialogDescription>
            Fill in the details to create a new item.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="title">Title *</Label>
            <Input
              id="title"
              placeholder="Enter title"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              className="mt-2"
            />
          </div>
          
          <div>
            <Label htmlFor="description">Description *</Label>
            <Textarea
              id="description"
              placeholder="Enter description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={6}
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="category">Category</Label>
            <Select value={formData.category} onValueChange={(value) => setFormData({ ...formData, category: value })}>
              <SelectTrigger id="category" className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bug">Bug</SelectItem>
                <SelectItem value="feature">Feature</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end gap-2 mt-6">
            <Button variant="secondary" onClick={handleCancel}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSubmit}>
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

#### Modal Best Practices
- **State Management**: Always use controlled state for dialog open/close status
- **Form Validation**: Validate required fields before submission and show appropriate error messages
- **Loading States**: Disable buttons and show loading indicators during async operations
- **Error Handling**: Use toast notifications for success/error feedback
- **Accessibility**: Dialog components are built with accessibility in mind - ensure proper ARIA labels
- **Responsive Design**: Use `max-w-*` classes to control modal width on different screen sizes
- **Form Reset**: Always reset form data when closing the modal (both on cancel and successful submit)
- **Consistent Styling**: Use the same button variants and spacing as shown in the examples
- **Toast Integration**: Use the `toast` hook from `@/hooks/use-toast` for user feedback

[Back to Index](./index.md)
