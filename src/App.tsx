import React from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthGuard } from "@/components/AuthGuard";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Organizations from "./pages/Organizations";
import OrganizationsOverview from "./pages/organizations/OrganizationsOverview";
import OrganizationDetail from "./pages/organizations/OrganizationDetail";
import OrganizationSettings from "./pages/organizations/OrganizationSettings";
import ProjectDetail from "./pages/organizations/ProjectDetail";
import EnvironmentDetail from "./pages/organizations/EnvironmentDetail";
import AppDetail from "./pages/organizations/AppDetail";
import AppWorkspacePage from "./pages/organizations/AppWorkspacePage";
import MyTeamspace from "./pages/MyTeamspace";
import ViewApplication from "./pages/ViewApplication";
import JoinApplication from "./pages/JoinApplication";
import ForkApplication from "./pages/ForkApplication";
import CreateWorkspaceProject from "./pages/CreateWorkspaceProject";
import MyApplications from "./pages/MyApplications";
import CreateApplication from "./pages/CreateApplication";
import EditApplication from "./pages/EditApplication";
import ApplicationPreview from "./pages/ApplicationPreview";
import ApprovalQueue from "./pages/ApprovalQueue";
import CollaborationHub from "./pages/CollaborationHub";
import Marketplace from "./pages/Marketplace";
import EnterpriseChatbot from "./pages/EnterpriseChatbot";
import SafetyCompliance from "./pages/SafetyCompliance";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";
import Support from "./pages/Support";
import About from "./pages/About";
import NotFound from "./pages/NotFound";
import CreateDiscussion from "./pages/CreateDiscussion";
import ViewDiscussion from "./pages/ViewDiscussion";
import CreateTeam from "./pages/CreateTeam";
import ViewTeam from "./pages/ViewTeam";
import JoinTeam from "./pages/JoinTeam";
import AdminWorkspaceSettings from "./pages/AdminWorkspaceSettings";
import LLMUsageReport from "./pages/LLMUsageReport";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<AuthGuard><Dashboard /></AuthGuard>} />
          <Route path="/organizations" element={<AuthGuard><Organizations /></AuthGuard>}>
            <Route index element={<OrganizationsOverview />} />
            <Route path=":orgId" element={<OrganizationDetail />} />
            <Route path=":orgId/settings" element={<OrganizationSettings />} />
            <Route path=":orgId/projects/:projectId" element={<ProjectDetail />} />
            <Route path=":orgId/projects/:projectId/environments/:environmentId" element={<EnvironmentDetail />} />
            <Route path=":orgId/projects/:projectId/environments/:environmentId/apps/:appId" element={<AppDetail />} />
          </Route>
          <Route
            path="/organizations/:orgId/projects/:projectId/environments/:environmentId/apps/:appId/workspace"
            element={<AuthGuard><AppWorkspacePage /></AuthGuard>}
          />
          <Route path="/my-teamspace" element={<AuthGuard><MyTeamspace /></AuthGuard>} />
          <Route path="/my-teamspace/view/:appName" element={<AuthGuard><ViewApplication /></AuthGuard>} />
          <Route path="/my-teamspace/join/:appName" element={<AuthGuard><JoinApplication /></AuthGuard>} />
          <Route path="/my-teamspace/fork/:appName" element={<AuthGuard><ForkApplication /></AuthGuard>} />
          <Route path="/my-teamspace/create" element={<AuthGuard><CreateWorkspaceProject /></AuthGuard>} />
          <Route path="/my-applications" element={<AuthGuard><MyApplications /></AuthGuard>} />
          <Route path="/my-applications/create" element={<AuthGuard><CreateApplication /></AuthGuard>} />
          <Route path="/my-applications/edit/:appName" element={<AuthGuard><EditApplication /></AuthGuard>} />
          <Route path="/my-applications/run/:appName" element={<AuthGuard><ApplicationPreview /></AuthGuard>} />
          <Route path="/approval-queue" element={<AuthGuard><ApprovalQueue /></AuthGuard>} />
          <Route path="/safety-compliance" element={<AuthGuard><SafetyCompliance /></AuthGuard>} />
          <Route path="/marketplace" element={<AuthGuard><Marketplace /></AuthGuard>} />
          <Route path="/enterprise-chatbot" element={<AuthGuard><EnterpriseChatbot /></AuthGuard>} />
          <Route path="/collaboration-hub" element={<AuthGuard><CollaborationHub /></AuthGuard>} />
          <Route path="/create-discussion" element={<AuthGuard><CreateDiscussion /></AuthGuard>} />
          <Route path="/view-discussion/:id" element={<AuthGuard><ViewDiscussion /></AuthGuard>} />
          <Route path="/create-team" element={<AuthGuard><CreateTeam /></AuthGuard>} />
          <Route path="/teams/view/:teamId" element={<AuthGuard><ViewTeam /></AuthGuard>} />
          <Route path="/teams/join/:teamId" element={<AuthGuard><JoinTeam /></AuthGuard>} />
          <Route path="/notifications" element={<AuthGuard><Notifications /></AuthGuard>} />
          <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
          <Route path="/admin/workspace-settings" element={<AuthGuard><AdminWorkspaceSettings /></AuthGuard>} />
          <Route path="/admin/llm-usage" element={<AuthGuard><LLMUsageReport /></AuthGuard>} />
          <Route path="/support" element={<AuthGuard><Support /></AuthGuard>} />
          <Route path="/about" element={<AuthGuard><About /></AuthGuard>} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<AuthGuard><NotFound /></AuthGuard>} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
