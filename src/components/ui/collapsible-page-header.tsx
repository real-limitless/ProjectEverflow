import React, { useState, useEffect } from 'react';
import { ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface CollapsiblePageHeaderProps {
  children: React.ReactNode;
  className?: string;
  /**
   * Scroll threshold in pixels before header starts hiding
   * @default 100
   */
  scrollThreshold?: number;
  /**
   * If true, header will not auto-hide on scroll
   * @default false
   */
  disabled?: boolean;
}

/**
 * CollapsiblePageHeader - Auto-hide header on scroll down, show on scroll up
 * 
 * This component implements a smart header that automatically hides when scrolling down
 * and reappears when scrolling up, maximizing vertical space for content.
 * 
 * @example
 * ```tsx
 * <CollapsiblePageHeader>
 *   <div className="p-6 border-b">
 *     <h1>My Page Title</h1>
 *     <Tabs>...</Tabs>
 *   </div>
 * </CollapsiblePageHeader>
 * ```
 */
export const CollapsiblePageHeader: React.FC<CollapsiblePageHeaderProps> = ({
  children,
  className,
  scrollThreshold = 100,
  disabled = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [lastScrollY, setLastScrollY] = useState(0);

  useEffect(() => {
    if (disabled) return;

    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      
      // Hide header when scrolling down past threshold
      if (currentScrollY > lastScrollY && currentScrollY > scrollThreshold) {
        setIsCollapsed(true);
      } 
      // Show header when scrolling up
      else if (currentScrollY < lastScrollY) {
        setIsCollapsed(false);
      }
      
      setLastScrollY(currentScrollY);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [lastScrollY, scrollThreshold, disabled]);

  return (
    <>
      <div
        className={cn(
          'sticky top-0 z-40 transition-transform duration-300 ease-in-out bg-background border-b',
          isCollapsed && !disabled ? '-translate-y-full' : 'translate-y-0',
          className
        )}
      >
        {children}
      </div>
      
      {/* Floating expand button when collapsed */}
      {isCollapsed && !disabled && (
        <Button
          variant="secondary"
          size="sm"
          className="fixed top-4 right-4 z-50 shadow-lg hover:shadow-xl transition-shadow"
          onClick={() => setIsCollapsed(false)}
        >
          <ChevronUp className="h-4 w-4 mr-2" />
          Show Header
        </Button>
      )}
    </>
  );
};
