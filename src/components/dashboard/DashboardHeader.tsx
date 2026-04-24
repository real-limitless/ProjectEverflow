import {
  Masthead,
  MastheadToggle,
  MastheadMain,
  MastheadBrand,
  MastheadContent,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
  Dropdown,
  DropdownList,
  DropdownItem,
  MenuToggle,
  Button,
  Avatar,
} from "@patternfly/react-core";
import { BarsIcon } from "@patternfly/react-icons";
import { MessageSquare } from "lucide-react";
import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { EnterpriseChatbotShell } from "@/components/chatbot/EnterpriseChatbotShell";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { logout } from "@/lib/api";

interface DashboardHeaderProps {
  onToggleSidebar: () => void;
}

export const DashboardHeader = ({ onToggleSidebar }: DashboardHeaderProps) => {
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isGlobalChatOpen, setIsGlobalChatOpen] = useState(false);
  const [username, setUsername] = useState("User");
  const navigate = useNavigate();
  const location = useLocation();
  const isEnterpriseChatbotPage = location.pathname === '/enterprise-chatbot';

  useEffect(() => {
    // Get username from localStorage (set during login)
    const storedUsername = localStorage.getItem('username');
    if (storedUsername) {
      setUsername(storedUsername);
    }
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Masthead>
      <MastheadMain>
        <MastheadToggle>
          <Button
            variant="plain"
            onClick={onToggleSidebar}
            aria-label="Toggle sidebar"
            style={{
              padding: "0.5rem",
              minWidth: "auto",
            }}
          >
            <BarsIcon />
          </Button>
        </MastheadToggle>
        <MastheadBrand style={{ marginLeft: "1rem" }}>
          <span style={{ fontSize: "1.25rem", fontWeight: 600 }}>Project Everflow</span>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar>
          <ToolbarContent>
            <ToolbarGroup align={{ default: "alignEnd" }}>
              {!isEnterpriseChatbotPage && (
                <ToolbarItem>
                  <Button
                    variant="plain"
                    onClick={() => setIsGlobalChatOpen(true)}
                    aria-label="Open global chat"
                    title="Open global chat"
                    icon={<MessageSquare size={18} aria-hidden="true" />}
                  />
                </ToolbarItem>
              )}
              <ToolbarItem>
                <Dropdown
                  isOpen={isUserMenuOpen}
                  onOpenChange={setIsUserMenuOpen}
                  toggle={(toggleRef) => (
                    <MenuToggle
                      ref={toggleRef}
                      onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                      icon={
                        <Avatar
                          src="https://www.patternfly.org/v4/images/img_avatar.svg"
                          alt={username}
                          size="sm"
                        />
                      }
                    >
                      {username}
                    </MenuToggle>
                  )}
                >
                  <DropdownList>
                    <DropdownItem>Profile</DropdownItem>
                    <DropdownItem>Settings</DropdownItem>
                    <DropdownItem onClick={handleLogout}>Logout</DropdownItem>
                  </DropdownList>
                </Dropdown>
              </ToolbarItem>
            </ToolbarGroup>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>

      {!isEnterpriseChatbotPage && (
        <Dialog open={isGlobalChatOpen} onOpenChange={setIsGlobalChatOpen}>
          <DialogContent className="w-[96vw] max-w-[1400px] overflow-hidden p-0">
            <div className="border-b border-border px-6 py-4">
              <DialogHeader>
                <DialogTitle>Global Chat</DialogTitle>
                <DialogDescription>
                  Continue conversations, switch personas, and launch templates from anywhere in the workspace.
                </DialogDescription>
              </DialogHeader>
            </div>
            <div className="px-6 pb-6 pt-4">
              <EnterpriseChatbotShell
                showPageHeader={false}
                containerClassName="h-[min(78vh,820px)] min-h-[560px]"
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Masthead>
  );
};
