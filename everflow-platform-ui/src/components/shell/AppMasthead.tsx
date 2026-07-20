import {
  Button,
  Divider,
  Label,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadLogo,
  MastheadMain,
  MastheadToggle,
  MenuToggle,
  PageToggleButton,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from '@patternfly/react-core'
import BarsIcon from '@patternfly/react-icons/dist/esm/icons/bars-icon'
import UserIcon from '@patternfly/react-icons/dist/esm/icons/user-icon'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function AppMasthead() {
  const resetLayout = usePlaygroundStore((s) => s.resetLayout)

  return (
    <Masthead id="page-masthead">
      <MastheadMain>
        <MastheadToggle>
          <PageToggleButton variant="plain" aria-label="Global navigation" id="navToggle">
            <BarsIcon />
          </PageToggleButton>
        </MastheadToggle>
        <MastheadBrand>
          <MastheadLogo
            href="/"
            className="masthead-brand-text"
            onClick={(e) => e.preventDefault()}
          >
            Project<span>Everflow</span>
          </MastheadLogo>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar id="page-toolbar" isStatic>
          <ToolbarContent>
            <ToolbarGroup
              align={{ default: 'alignEnd' }}
              gap={{ default: 'gapMd' }}
              alignItems="center"
            >
              <ToolbarItem>
                <Button
                  variant="link"
                  onClick={() => resetLayout()}
                  title="Reset layout"
                  aria-label="Reset layout"
                >
                  Reset layout
                </Button>
              </ToolbarItem>
              <ToolbarItem>
                <Divider orientation={{ default: 'vertical' }} />
              </ToolbarItem>
              <ToolbarItem>
                <Label color="blue" variant="outline">
                  Playground
                </Label>
              </ToolbarItem>
              <ToolbarItem>
                <MenuToggle
                  className="pg-user-toggle"
                  variant="plain"
                  icon={<UserIcon />}
                  isFullHeight
                >
                  admin
                </MenuToggle>
              </ToolbarItem>
            </ToolbarGroup>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  )
}
