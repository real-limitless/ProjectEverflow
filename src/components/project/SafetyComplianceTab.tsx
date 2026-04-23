import { useState } from 'react';
import { Card, CardBody, CardTitle, Button } from '@patternfly/react-core';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from '@/hooks/use-toast';
import { Shield, Layers, CheckCircle, AlertTriangle, XCircle, ListChecks } from 'lucide-react';
import complianceData from '@/data/complianceChecks.json';

interface SafetyComplianceTabProps {
  projectName: string;
}

export const SafetyComplianceTab: React.FC<SafetyComplianceTabProps> = ({ projectName }) => {
  const [assignedTemplates, setAssignedTemplates] = useState<string[]>([]);
  const [assignedChecks, setAssignedChecks] = useState<string[]>([]);
  const [isRunningChecks, setIsRunningChecks] = useState(false);
  const [checkResults, setCheckResults] = useState<Array<{
    checkId: string;
    checkName: string;
    status: 'Pass' | 'Warning' | 'Fail';
    message: string;
    remediation: string;
  }>>([]);
  const [isAssignDialogOpen, setIsAssignDialogOpen] = useState(false);
  const [selectedTemplatesForAssign, setSelectedTemplatesForAssign] = useState<string[]>([]);

  const handleAssignTemplates = () => {
    setAssignedTemplates(selectedTemplatesForAssign);
    
    // Also add all checks from selected templates
    const checksFromTemplates = selectedTemplatesForAssign.flatMap(templateId => {
      const template = complianceData.templates.find(t => t.id === templateId);
      return template ? template.checks : [];
    });
    
    setAssignedChecks(prev => [...new Set([...prev, ...checksFromTemplates])]);
    
    toast({
      title: "Templates Assigned",
      description: `${selectedTemplatesForAssign.length} compliance template(s) assigned to this project.`,
    });
    
    setIsAssignDialogOpen(false);
    setSelectedTemplatesForAssign([]);
  };

  const handleToggleCheck = (checkId: string) => {
    setAssignedChecks(prev => 
      prev.includes(checkId) 
        ? prev.filter(id => id !== checkId)
        : [...prev, checkId]
    );
  };

  const handleRunChecks = async () => {
    if (assignedChecks.length === 0) {
      toast({
        title: "No Checks Assigned",
        description: "Please assign templates or checks before running compliance checks.",
        variant: "destructive",
      });
      return;
    }

    setIsRunningChecks(true);
    
    // Simulate running checks
    setTimeout(() => {
      const results = assignedChecks.map(checkId => {
        const check = complianceData.checks.find(c => c.id === checkId);
        if (!check) return null;
        
        // Simulate random results for demo
        const statuses: Array<'Pass' | 'Warning' | 'Fail'> = ['Pass', 'Warning', 'Fail'];
        const randomStatus = statuses[Math.floor(Math.random() * statuses.length)];
        
        return {
          checkId: check.id,
          checkName: check.name,
          status: randomStatus,
          message: randomStatus === 'Pass' 
            ? `${check.name} passed successfully.`
            : randomStatus === 'Warning'
            ? `${check.name} completed with warnings.`
            : `${check.name} failed validation.`,
          remediation: check.aiPrompt,
        };
      }).filter(Boolean) as typeof checkResults;
      
      setCheckResults(results);
      setIsRunningChecks(false);
      
      const passCount = results.filter(r => r.status === 'Pass').length;
      const failCount = results.filter(r => r.status === 'Fail').length;
      const warningCount = results.filter(r => r.status === 'Warning').length;
      
      toast({
        title: "Compliance Checks Complete",
        description: `${passCount} passed, ${warningCount} warnings, ${failCount} failed`,
      });
    }, 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <Card>
        <CardBody>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1.5rem' }}>
            <div>
              <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Shield size={24} />
                Safety and Compliance Checks
              </CardTitle>
              <p style={{ fontSize: '0.9375rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                Assign compliance templates and run automated checks against your project
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <Dialog open={isAssignDialogOpen} onOpenChange={setIsAssignDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="secondary">
                    <Layers size={16} style={{ marginRight: '0.25rem' }} />
                    Assign Templates
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Assign Compliance Templates</DialogTitle>
                  </DialogHeader>
                  
                  <div className="space-y-4 py-4">
                    {complianceData.templates.map(template => (
                      <div key={template.id} className="flex items-start space-x-3 p-3 border rounded">
                        <Checkbox
                          checked={selectedTemplatesForAssign.includes(template.id)}
                          onCheckedChange={(checked) => {
                            if (checked) {
                              setSelectedTemplatesForAssign(prev => [...prev, template.id]);
                            } else {
                              setSelectedTemplatesForAssign(prev => prev.filter(id => id !== template.id));
                            }
                          }}
                        />
                        <div className="flex-1">
                          <h4 className="font-semibold">{template.name}</h4>
                          <p className="text-sm text-muted-foreground">{template.description}</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            {template.checks.length} checks included
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="flex justify-end gap-2">
                    <Button variant="secondary" onClick={() => setIsAssignDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button variant="primary" onClick={handleAssignTemplates}>
                      Assign Templates
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
              
              <Button 
                variant="primary" 
                onClick={handleRunChecks}
                isDisabled={isRunningChecks || assignedChecks.length === 0}
              >
                {isRunningChecks ? (
                  <>Running Checks...</>
                ) : (
                  <>
                    <ListChecks size={16} style={{ marginRight: '0.25rem' }} />
                    Run Checks
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Assigned Templates Summary */}
          {assignedTemplates.length > 0 && (
            <div style={{ 
              padding: '1rem',
              backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
              borderRadius: '8px',
              marginBottom: '1rem'
            }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Assigned Templates:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                {assignedTemplates.map(templateId => {
                  const template = complianceData.templates.find(t => t.id === templateId);
                  return template ? <Badge key={templateId} variant="secondary">{template.name}</Badge> : null;
                })}
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                {assignedChecks.length} checks will be run
              </div>
            </div>
          )}

          {assignedChecks.length === 0 && (
            <div style={{
              textAlign: 'center',
              padding: '3rem 1rem',
              color: 'var(--pf-v6-global--Color--200)',
              backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
              borderRadius: '8px'
            }}>
              <Shield size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                No Compliance Checks Assigned
              </p>
              <p style={{ fontSize: '0.875rem' }}>
                Assign compliance templates to automatically validate your project against security and compliance standards
              </p>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Check Results */}
      {checkResults.length > 0 && (
        <Card>
          <CardBody>
            <CardTitle style={{ marginBottom: '1rem' }}>
              Check Results
            </CardTitle>
            
            {/* Summary Stats */}
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ 
                flex: 1,
                padding: '1rem',
                backgroundColor: '#d1fae5',
                borderRadius: '8px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#065f46' }}>
                  {checkResults.filter(r => r.status === 'Pass').length}
                </div>
                <div style={{ fontSize: '0.875rem', color: '#065f46' }}>Passed</div>
              </div>
              <div style={{ 
                flex: 1,
                padding: '1rem',
                backgroundColor: '#fef3c7',
                borderRadius: '8px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#92400e' }}>
                  {checkResults.filter(r => r.status === 'Warning').length}
                </div>
                <div style={{ fontSize: '0.875rem', color: '#92400e' }}>Warnings</div>
              </div>
              <div style={{ 
                flex: 1,
                padding: '1rem',
                backgroundColor: '#fee2e2',
                borderRadius: '8px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#991b1b' }}>
                  {checkResults.filter(r => r.status === 'Fail').length}
                </div>
                <div style={{ fontSize: '0.875rem', color: '#991b1b' }}>Failed</div>
              </div>
            </div>

            {/* Detailed Results */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {checkResults.map((result) => (
                <div
                  key={result.checkId}
                  style={{
                    padding: '1rem',
                    border: '1px solid var(--pf-v6-global--BorderColor--100)',
                    borderRadius: '8px',
                    backgroundColor: '#ffffff'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.5rem' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        {result.status === 'Pass' && <CheckCircle size={18} color="#10b981" />}
                        {result.status === 'Warning' && <AlertTriangle size={18} color="#f59e0b" />}
                        {result.status === 'Fail' && <XCircle size={18} color="#ef4444" />}
                        <span style={{ fontWeight: 600 }}>{result.checkName}</span>
                      </div>
                      <p style={{ fontSize: '0.875rem', marginBottom: '0.5rem' }}>{result.message}</p>
                      {result.status !== 'Pass' && (
                        <div style={{ 
                          fontSize: '0.8125rem', 
                          padding: '0.5rem', 
                          backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                          borderRadius: '4px',
                          marginTop: '0.5rem'
                        }}>
                          <strong>Remediation:</strong> {result.remediation}
                        </div>
                      )}
                    </div>
                    <Badge variant={
                      result.status === 'Pass' ? 'default' :
                      result.status === 'Warning' ? 'secondary' : 'destructive'
                    }>
                      {result.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Individual Check Management */}
      {assignedChecks.length > 0 && (
        <Card>
          <CardBody>
            <CardTitle style={{ marginBottom: '1rem' }}>
              Assigned Checks ({assignedChecks.length})
            </CardTitle>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {assignedChecks.map(checkId => {
                const check = complianceData.checks.find(c => c.id === checkId);
                if (!check) return null;
                
                return (
                  <div
                    key={checkId}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '0.75rem',
                      border: '1px solid var(--pf-v6-global--BorderColor--100)',
                      borderRadius: '6px'
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <span style={{ fontWeight: 500 }}>{check.name}</span>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)' }}>
                        <Badge variant="outline" style={{ marginRight: '0.5rem' }}>{check.category}</Badge>
                        <Badge variant="outline">{check.severity}</Badge>
                      </div>
                    </div>
                    <Button 
                      variant="danger"
                      size="sm"
                      onClick={() => handleToggleCheck(checkId)}
                    >
                      Remove
                    </Button>
                  </div>
                );
              })}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
};
