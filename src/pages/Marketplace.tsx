import { useState, useRef, useEffect } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Grid, GridItem, Button, TextInput, Label } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Sparkles, Search, Image, Video, FileText, Languages, Mic, Box, Eye, FileSearch, Wand2, Code, HelpCircle, BarChart3, ChevronLeft, ChevronRight, Heart, Loader2, AlertCircle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getMarketplaceCategories, getMarketplaceItems, likeMarketplaceItem, MarketplaceCategory, MarketplaceItem } from '@/lib/api';
import { toast } from '@/hooks/use-toast';
import PageHeader from '@/components/ui/PageHeader';

// Icon mapping
const iconMap: { [key: string]: any } = {
  Image,
  Video,
  FileText,
  Languages,
  Mic,
  Box,
  Eye,
  FileSearch,
  Code,
  HelpCircle,
  BarChart3,
  Sparkles
};

// Function to determine if a color is light or dark
const isLightColor = (gradient: string): boolean => {
  // Extract the first color from the gradient (the dominant one)
  const colorMatch = gradient.match(/#([0-9a-f]{6})/i);
  if (!colorMatch) return false;
  
  const hex = colorMatch[1];
  const r = parseInt(hex.substr(0, 2), 16);
  const g = parseInt(hex.substr(2, 2), 16);
  const b = parseInt(hex.substr(4, 2), 16);
  
  // Calculate relative luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  
  // If luminance is greater than 0.5, it's a light color
  return luminance > 0.5;
};

const Marketplace = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(true);

  const handleScroll = (direction: 'left' | 'right') => {
    if (scrollContainerRef.current) {
      const scrollAmount = 300;
      const newScrollLeft = scrollContainerRef.current.scrollLeft + (direction === 'right' ? scrollAmount : -scrollAmount);
      scrollContainerRef.current.scrollTo({ left: newScrollLeft, behavior: 'smooth' });
    }
  };

  const checkScrollPosition = () => {
    if (scrollContainerRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollContainerRef.current;
      setShowLeftArrow(scrollLeft > 0);
      setShowRightArrow(scrollLeft < scrollWidth - clientWidth - 10);
    }
  };

  useEffect(() => {
    checkScrollPosition();
    const handleResize = () => checkScrollPosition();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Fetch marketplace categories
  const { data: categoriesResponse, isLoading: isLoadingCategories, error: errorCategories, refetch: refetchCategories } = useQuery({
    queryKey: ['marketplace-categories'],
    queryFn: getMarketplaceCategories,
  });

  // Fetch marketplace items with filters
  const { data: itemsResponse, isLoading: isLoadingItems, error: errorItems, refetch: refetchItems } = useQuery({
    queryKey: ['marketplace-items', selectedCategory, searchQuery],
    queryFn: () => getMarketplaceItems({
      category: selectedCategory,
      search: searchQuery,
    }),
  });

  const categories = categoriesResponse?.data || [];
  const tools = itemsResponse?.data || [];

  const filteredTools = tools.filter((tool: MarketplaceItem) =>
    (selectedCategory === 'all' || tool.category === selectedCategory) &&
    (tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
     tool.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Get current week date range
  const getCurrentWeek = () => {
    const now = new Date();
    const startOfWeek = new Date(now);
    startOfWeek.setDate(now.getDate() - now.getDay());
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);
    
    const formatDate = (date: Date) => {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };
    
    return `${formatDate(startOfWeek)} - ${formatDate(endOfWeek)}`;
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default" style={{ backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>
        <PageHeader
          title="Enterprise AI Marketplace"
          description="Discover and use AI applications published across your organization. Fork tools to your workspace to customize them."
          icon={<Wand2 size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        {/* Search Bar */}
        <div style={{
          marginBottom: '2rem',
          backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
          padding: '1.5rem',
          borderRadius: '8px',
          border: '1px solid var(--pf-v6-global--BorderColor--100)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Sparkles size={20} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />
            <TextInput
              type="text"
              placeholder="Ask anything you want to do with AI..."
              value={searchQuery}
              onChange={(_event, value) => setSearchQuery(value)}
              style={{ flex: 1 }}
            />
            <Search size={20} style={{ color: 'var(--pf-v6-global--Color--200)' }} />
          </div>
        </div>

        {/* Category Filters with Arrow Navigation */}
        <div style={{ position: 'relative', marginBottom: '2rem', paddingLeft: '2rem', paddingRight: '2rem' }}>
          {showLeftArrow && (
            <Button
              variant="primary"
              onClick={() => handleScroll('left')}
              aria-label="Scroll left"
              style={{
                position: 'absolute',
                left: 0,
                top: '50%',
                transform: 'translateY(-50%)',
                zIndex: 10,
                width: '36px',
                height: '36px',
                minWidth: '36px',
                borderRadius: '50%',
                padding: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
              }}
            >
              <ChevronLeft size={18} />
            </Button>
          )}
          
          <div 
            ref={scrollContainerRef}
            onScroll={checkScrollPosition}
            style={{ 
              overflowX: 'auto',
              whiteSpace: 'nowrap',
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
              WebkitOverflowScrolling: 'touch',
              paddingBottom: '0.5rem'
            }}
            className="hide-scrollbar"
          >
            <style>{`
              .hide-scrollbar::-webkit-scrollbar {
                display: none;
              }
              .category-button {
                display: inline-flex !important;
                align-items: center !important;
                flex-direction: row !important;
              }
            `}</style>
            <div style={{ display: 'inline-flex', gap: '0.75rem', paddingLeft: '0.25rem', paddingRight: '0.25rem' }}>
              {categories.map((category) => {
                const IconComponent = iconMap[category.icon] || Sparkles;
                const isSelected = selectedCategory === category.id;
                return (
                  <Button
                    key={category.id}
                    variant={isSelected ? 'primary' : 'secondary'}
                    onClick={() => setSelectedCategory(category.id)}
                    className="category-button"
                    style={{ 
                      whiteSpace: 'nowrap',
                      padding: '0.5rem 1.25rem',
                      borderRadius: '24px',
                      fontSize: '0.9rem',
                      fontWeight: 500,
                      border: isSelected ? 'none' : '1px solid var(--pf-v6-global--BorderColor--100)',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                      <IconComponent size={16} />
                      <span>{category.label}</span>
                    </span>
                  </Button>
                );
              })}
            </div>
          </div>

          {showRightArrow && (
            <Button
              variant="primary"
              onClick={() => handleScroll('right')}
              aria-label="Scroll right"
              style={{
                position: 'absolute',
                right: 0,
                top: '50%',
                transform: 'translateY(-50%)',
                zIndex: 10,
                width: '36px',
                height: '36px',
                minWidth: '36px',
                borderRadius: '50%',
                padding: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
              }}
            >
              <ChevronRight size={18} />
            </Button>
          )}
        </div>

        {/* Tools of the Week Header */}
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: '1.5rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              🔥 Featured This Week
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.9rem', color: 'var(--pf-v6-global--Color--200)' }}>
                {getCurrentWeek()}
              </span>
            </div>
          </div>
          <div style={{ fontSize: '0.9rem', color: 'var(--pf-v6-global--Color--200)' }}>
            {filteredTools.length} tools found
          </div>
        </div>

        {/* Loading State */}
        {isLoadingCategories || isLoadingItems ? (
          <div style={{ 
            textAlign: 'center', 
            padding: '3rem',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '300px'
          }}>
            <div style={{ 
              width: '40px', 
              height: '40px', 
              border: '4px solid var(--pf-v6-global--BorderColor--100)', 
              borderTop: '4px solid var(--pf-v6-global--primary--Color--100)', 
              borderRadius: '50%', 
              animation: 'spin 1s linear infinite',
              marginBottom: '1rem'
            }} />
            <p style={{ color: 'var(--pf-v6-global--Color--200)' }}>Loading marketplace...</p>
            <style>{`
              @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        ) : errorCategories || errorItems ? (
          /* Error State */
          <div style={{ 
            textAlign: 'center', 
            padding: '3rem',
            color: 'var(--pf-v6-global--Color--200)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '300px'
          }}>
            <AlertCircle size={48} style={{ marginBottom: '1rem', color: 'var(--pf-v6-global--danger--Color--100)' }} />
            <h3 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', color: 'var(--pf-v6-global--danger--Color--100)' }}>
              Failed to load marketplace
            </h3>
            <p style={{ marginBottom: '1rem' }}>
              {errorCategories?.message || errorItems?.message || 'An error occurred while loading the marketplace.'}
            </p>
            <Button 
              variant="primary" 
              onClick={() => {
                refetchCategories();
                refetchItems();
              }}
            >
              Try Again
            </Button>
          </div>
        ) : (
          /* Tools Grid */
          <>
            <Grid hasGutter>
              {filteredTools.map((tool, idx) => {
                const isLight = isLightColor(tool.gradient);
                // Always use white text for better consistency
                const textColor = 'white';
                const labelBgColor = 'rgba(255, 255, 255, 0.2)';
                const borderColor = 'rgba(255, 255, 255, 0.2)';
                // Add overlay for dark gradients to improve readability
                const overlayOpacity = isLight ? 0.15 : 0.35;
                
                return (
                  <GridItem key={idx} span={12} md={6} lg={4} xl={3}>
                    <Card 
                      style={{ 
                        background: tool.gradient,
                        border: 'none',
                        color: textColor,
                        height: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        cursor: 'pointer',
                        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                        position: 'relative',
                        overflow: 'hidden',
                        minHeight: '280px'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-4px)';
                        e.currentTarget.style.boxShadow = '0 8px 16px rgba(0, 0, 0, 0.2)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}
                    >
                      {/* Dark overlay for better text readability */}
                      <div style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: `linear-gradient(135deg, rgba(0, 0, 0, ${overlayOpacity}) 0%, rgba(0, 0, 0, ${overlayOpacity * 0.6}) 100%)`,
                        zIndex: 0,
                        pointerEvents: 'none'
                      }} />
                      
                      <div style={{ 
                        position: 'absolute',
                        top: '1rem',
                        left: '1rem',
                        right: '1rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: '0.5rem',
                        zIndex: 1
                      }}>
                        <Label 
                          style={{ 
                            backgroundColor: labelBgColor,
                            color: textColor,
                            border: 'none',
                            fontSize: '0.7rem',
                            padding: '0.25rem 0.625rem',
                            borderRadius: '12px',
                            fontWeight: 600,
                            backdropFilter: 'blur(8px)'
                          }}
                        >
                          {tool.status}
                        </Label>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '0.375rem',
                          backgroundColor: labelBgColor,
                          padding: '0.25rem 0.625rem',
                          borderRadius: '12px',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          backdropFilter: 'blur(8px)',
                          color: textColor
                        }}>
                          <Heart size={12} fill={textColor} />
                          {tool.likes}
                        </div>
                      </div>
                      <CardBody style={{ 
                        marginTop: '3.5rem',
                        flex: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        color: textColor,
                        padding: '1.25rem',
                        position: 'relative',
                        zIndex: 1
                      }}>
                        <CardTitle style={{ 
                          fontSize: '1.35rem', 
                          fontWeight: 700,
                          color: textColor,
                          marginBottom: '0.875rem',
                          lineHeight: '1.3',
                          textShadow: '0 2px 8px rgba(0, 0, 0, 0.3)'
                        }}>
                          {tool.name} {tool.emoji}
                        </CardTitle>
                        <p style={{ 
                          fontSize: '0.9rem',
                          lineHeight: '1.6',
                          flex: 1,
                          marginBottom: '1rem',
                          opacity: 0.95,
                          textShadow: '0 1px 4px rgba(0, 0, 0, 0.3)'
                        }}>
                          {tool.description}
                        </p>
                        <div style={{ 
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          fontSize: '0.8rem',
                          opacity: 0.9,
                          paddingTop: '0.875rem',
                          borderTop: `1px solid ${borderColor}`,
                          fontWeight: 500
                        }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                            <span style={{ fontSize: '1rem' }}>👤</span> {tool.author.first_name} {tool.author.last_name}
                          </span>
                          <span>{new Date(tool.created_at).toLocaleDateString()}</span>
                        </div>
                      </CardBody>
                    </Card>
                  </GridItem>
                );
              })}
            </Grid>

            {/* Empty State */}
            {filteredTools.length === 0 && (
              <div style={{ 
                textAlign: 'center', 
                padding: '3rem',
                color: 'var(--pf-v6-global--Color--200)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '300px'
              }}>
                <Sparkles size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
                <h3 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No tools found</h3>
                <p>Try adjusting your search or filter criteria</p>
              </div>
            )}
          </>
        )}
      </PageSection>
    </Page>
  );
};

export default Marketplace;



