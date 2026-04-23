import React, { useState } from 'react';
import { ChevronsUp, ChevronsDown, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Button as PFButton } from '@patternfly/react-core';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { cn } from '@/lib/utils';

interface CompactPageHeaderProps {
  title: string;
  subtitle?: string;
  backLink?: {
    label: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
  tabs?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  /**
   * If true, header starts in compact mode
   * @default false
   */
  defaultCompact?: boolean;
  className?: string;
}

/**
 * CompactPageHeader - Manually toggle between full and compact header modes
 * 
 * This component provides a header that can be manually collapsed to save vertical space.
 * Users can toggle between full mode (with all details) and compact mode (minimal info).
 * 
 * @example
 * ```tsx
 * <CompactPageHeader
 *   title="Edit Application"
 *   subtitle="Project Everflow"
 *   backLink={{ label: "Back to My Projects", onClick: () => navigate('/my-applications') }}
 *   tabs={<Tabs>...</Tabs>}
 * >
 *   <div>Custom header content</div>
 * </CompactPageHeader>
 * ```
 */
export const CompactPageHeader: React.FC<CompactPageHeaderProps> = ({
  title,
  subtitle,
  backLink,
  tabs,
  actions,
  children,
  defaultCompact = false,
  className,
}) => {
  const [isCompact, setIsCompact] = useState(defaultCompact);

  return (
    <div className={cn('sticky top-0 z-40 ', className)}>
      {/* Compact Mode */}
      {isCompact ? (
        <div className="flex items-center justify-between px-6 py-3 border-b">
          <div className="flex items-center gap-4 min-w-0 flex-1">
            {backLink && (
              <PFButton
                variant="plain"
                icon={<ArrowLeftIcon />}
                onClick={backLink.onClick}
                style={{ minWidth: 'auto', padding: '0.5rem' }}
              />
            )}
            <div className="min-w-0 flex items-center gap-3">
              <h1 className="text-lg font-semibold truncate">{title}</h1>
              {subtitle && (
                <>
                  <span className="text-muted-foreground shrink-0">•</span>
                  <span className="text-sm text-muted-foreground truncate">{subtitle}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {actions}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsCompact(false)}
            >
              <ChevronsDown className="h-4 w-4 mr-2" />
              Expand
            </Button>
          </div>
        </div>
      ) : (
        /* Full Mode */
        <div className="space-y-0">
          <div className="px-6 pt-6 pb-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                {backLink && (
                  <PFButton
                    variant="link"
                    icon={<ArrowLeftIcon />}
                    onClick={backLink.onClick}
                    style={{ padding: 0, marginBottom: '1rem' }}
                  >
                    {backLink.label}
                  </PFButton>
                )}
                <h1 className="text-3xl font-bold mb-2">{title}</h1>
                {subtitle && (
                  <p className="text-muted-foreground">{subtitle}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {actions}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsCompact(true)}
                >
                  <ChevronsUp className="h-4 w-4 mr-2" />
                  Compact
                </Button>
              </div>
            </div>
            {children}
          </div>
        </div>
      )}
      
      {/* Tabs always visible */}
      {tabs && (
        <div className={cn(
          "px-6",
          isCompact ? "py-0" : "border-t"
        )}>
          {tabs}
        </div>
      )}
    </div>
  );
};
