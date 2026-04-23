import { PageSidebar, PageSidebarBody, Nav, NavList, NavItem } from '@patternfly/react-core';
import { HomeIcon, FolderIcon, CubeIcon, ListIcon, UsersIcon, WrenchIcon, BellIcon, CogIcon, QuestionCircleIcon, InfoCircleIcon, SecurityIcon } from '@patternfly/react-icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { MessageSquare } from 'lucide-react';
import navigationData from '@/data/navigationData.json';

interface DashboardSidebarProps {
  isOpen: boolean;
}

const LucideIconWrapper = ({ Icon }: { Icon: React.ComponentType<{ size?: number }> }) => (
  <Icon size={16} />
);

const iconMap = {
  HomeIcon,
  FolderIcon,
  CubeIcon,
  ListIcon,
  UsersIcon,
  WrenchIcon,
  BellIcon,
  CogIcon,
  QuestionCircleIcon,
  InfoCircleIcon,
  SecurityIcon,
  MessageSquare
};

export const DashboardSidebar = ({ isOpen }: DashboardSidebarProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <PageSidebar isSidebarOpen={isOpen}>
      <PageSidebarBody>
        <Nav>
          <NavList>
            {navigationData.menuItems.map((item) => {
              const IconComponent = iconMap[item.icon as keyof typeof iconMap];
              return (
                <NavItem 
                  key={item.id}
                  itemId={item.id} 
                  isActive={location.pathname === item.path}
                  icon={item.isLucide ? <LucideIconWrapper Icon={IconComponent as any} /> : <IconComponent />}
                  onClick={() => navigate(item.path)}
                >
                  {item.title}
                </NavItem>
              );
            })}
          </NavList>
        </Nav>
      </PageSidebarBody>
    </PageSidebar>
  );
};
