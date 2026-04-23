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
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "@/lib/api";

interface DashboardHeaderProps {
  onToggleSidebar: () => void;
}

export const DashboardHeader = ({ onToggleSidebar }: DashboardHeaderProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [username, setUsername] = useState("User");
  const navigate = useNavigate();

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
              <ToolbarItem>
                <Dropdown
                  isOpen={isOpen}
                  onOpenChange={setIsOpen}
                  toggle={(toggleRef) => (
                    <MenuToggle
                      ref={toggleRef}
                      onClick={() => setIsOpen(!isOpen)}
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
    </Masthead>
  );
};
