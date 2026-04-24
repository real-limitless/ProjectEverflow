// API utility functions for backend communication
export const API_BASE_URL = 'http://localhost:8000/api';

// Simple logger utility for client-side logging
const logger = {
  error: (msg: string, error?: any) => console.error(`[API Error] ${msg}`, error),
  warn: (msg: string, error?: any) => console.warn(`[API Warning] ${msg}`, error),
  info: (msg: string) => console.log(`[API Info] ${msg}`),
  debug: (msg: string, data?: any) => console.debug(`[API Debug] ${msg}`, data),
};

// Flag to prevent multiple refresh attempts
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: any) => void;
}> = [];

// Process queued requests after refresh
const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token!);
    }
  });
  failedQueue = [];
};

// Helper to handle auth failure
const handleAuthFailure = () => {
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('isAuthenticated');
  localStorage.removeItem('username');
  // Redirect to login
  window.location.href = '/login';
};

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
}

interface PaginatedApiListResponse<T> {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: T[];
}

export function normalizeApiList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }

  if (payload && typeof payload === 'object') {
    const objectPayload = payload as { data?: unknown; results?: unknown };
    if (Array.isArray(objectPayload.data)) {
      return objectPayload.data as T[];
    }
    if (Array.isArray(objectPayload.results)) {
      return objectPayload.results as T[];
    }
  }

  return [];
}

export interface LoginResponse {
  access: string;
  refresh: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_staff?: boolean;
  bio?: string;
  avatar?: string;
  teams?: any[];
  email_notifications: boolean;
  dark_mode: boolean;
  default_llm_model?: string;
}

export interface Team {
  id: number;
  name: string;
  description: string;
  organization?: Organization | null;
  members: User[];
  member_count: number;
  created_at: string;
  updated_at: string;
}

export type OrganizationRole = 'owner' | 'admin' | 'member';

export interface OrganizationMembership {
  id: number;
  organization: number;
  organization_name: string;
  user: User;
  role: OrganizationRole;
  created_at: string;
  updated_at: string;
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  description: string;
  owner: User;
  memberships: OrganizationMembership[];
  member_count: number;
  project_count: number;
  user_role?: OrganizationRole | null;
  created_at: string;
  updated_at: string;
}

export type GitProviderType = 'github' | 'gitlab' | 'bitbucket' | 'gitea' | 'generic-git';
export type GitConnectionAuthType = 'pat' | 'oauth' | 'app' | 'ssh';
export type GitConnectionScope = 'organization' | 'personal';

export interface OrganizationGitConnection {
  id: number;
  organization: number;
  organization_name: string;
  name: string;
  provider_type: GitProviderType;
  auth_type: GitConnectionAuthType;
  base_url?: string | null;
  notes: string;
  repository_cache: string[];
  repository_count: number;
  webhook_enabled: boolean;
  last_tested_at?: string | null;
  last_test_status: 'unknown' | 'succeeded' | 'failed';
  credential_masked?: string | null;
  has_credentials: boolean;
  created_by?: number | null;
  created_by_username?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonalGitConnection {
  id: number;
  user: number;
  user_username: string;
  name: string;
  provider_type: GitProviderType;
  auth_type: GitConnectionAuthType;
  base_url?: string | null;
  notes: string;
  repository_cache: string[];
  repository_count: number;
  webhook_enabled: boolean;
  last_tested_at?: string | null;
  last_test_status: 'unknown' | 'succeeded' | 'failed';
  credential_masked?: string | null;
  has_credentials: boolean;
  created_at: string;
  updated_at: string;
}

export interface GitConnectionRepository {
  id: string;
  name: string;
  full_name: string;
  clone_url: string;
  ssh_url: string;
  web_url: string;
  default_branch: string;
  private: boolean;
}

export interface GitConnectionBranch {
  name: string;
  is_default: boolean;
  protected?: boolean;
}

export interface GitConnectionRepositoryList {
  repositories: GitConnectionRepository[];
  count: number;
}

export interface GitConnectionBranchList {
  repository: GitConnectionRepository | null;
  default_branch?: string | null;
  branches: GitConnectionBranch[];
  count: number;
}

export interface AppSourceSettings {
  id: number;
  app: number;
  source_type: ProjectApp['source_type'];
  repository_url: string;
  compose_path: string;
  connection_scope: GitConnectionScope | '';
  organization_connection?: number | null;
  organization_connection_name?: string | null;
  personal_connection?: number | null;
  personal_connection_name?: string | null;
  selected_connection_name?: string | null;
  selected_connection_provider?: GitProviderType | null;
  source_provider: GitProviderType | 'raw-compose' | 'docker-registry';
  source_ref: string;
  watch_paths: string[];
  trigger_type: 'manual' | 'push' | 'schedule';
  auto_deploy_enabled: boolean;
  creation_method?: 'blank' | 'clone' | 'chat' | 'template';
  git_repo_url?: string;
  branch?: string;
  provisioning_status?: 'pending' | 'in_progress' | 'completed' | 'failed';
  template?: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectEnvironment {
  id: number;
  project: number;
  project_name: string;
  organization_id?: number | null;
  name: string;
  slug: string;
  description: string;
  environment_type: 'production' | 'development' | 'staging' | 'demo' | 'custom';
  workspace_image: 'fedora:43' | 'registry.access.redhat.com/ubi9/ubi';
  workspace_size: string;
  workspace_mode: 'personal' | 'shared';
  domain?: string;
  is_primary: boolean;
  created_by?: User | null;
  app_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectApp {
  id: number;
  environment: number;
  environment_name: string;
  project_id: number;
  name: string;
  slug: string;
  description: string;
  source_type: 'compose' | 'container' | 'repository' | 'custom';
  repository_url?: string;
  compose_path?: string;
  status: 'draft' | 'active' | 'archived';
  config: Record<string, any>;
  created_by?: User | null;
  service_count: number;
  latest_deployment?: {
    id: number;
    version: string;
    status: string;
    created_at: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface DeploymentRecord {
  id: number;
  environment: number;
  environment_name: string;
  app: number;
  app_name: string;
  version: string;
  status: 'pending' | 'in_progress' | 'succeeded' | 'failed' | 'rolled_back';
  trigger_type: 'manual' | 'push' | 'rollback';
  deployed_by?: User | null;
  source_ref?: string;
  compose_path?: string;
  notes?: string;
  config_snapshot: Record<string, any>;
  service_snapshot: Record<string, any>;
  rollback_of?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type ChatMode = 'ask' | 'plan' | 'agent' | 'persona' | 'deep';

export interface ProjectService {
  id: number;
  pod: number;
  app?: number | null;
  name: string;
  service_type: 'backend' | 'frontend' | 'tooling' | 'custom' | 'ai-workspace';
  image: string;
  container_name: string;
  status: string;
  ports: string[];
  environment: Record<string, string>;
  config: Record<string, any>;
  autostart?: boolean;
  cpu_limit?: string;
  memory_limit?: string;
  last_started_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectPod {
  id: number;
  project: number;
  pod_name: string;
  status: string;
  config: Record<string, any>;
  last_synced_at?: string;
  created_at: string;
  updated_at: string;
  services: ProjectService[];
}

export interface ProjectTool {
  id: number;
  project: number;
  name: string;
  slug: string;
  description?: string;
  entrypoint: string;
  runtime_image?: string;
  args_schema?: Record<string, any>;
  environment?: Record<string, string>;
  timeout_seconds: number;
  is_active: boolean;
  created_by?: number;
  created_at: string;
  updated_at: string;
}

export interface ToolExecution {
  id: number;
  tool: ProjectTool;
  session: number | null;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  input_payload: Record<string, any>;
  output_payload?: Record<string, any>;
  logs?: string;
  exit_code?: number | null;
  started_at: string;
  completed_at?: string;
}

export interface ProjectTemplate {
  id: number;
  name: string;
  description: string;
  language: string;
  framework: string;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  tags: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Approval {
  id: number;
  approver: User;
  approved: boolean;
  comments: string;
  created_at: string;
  updated_at: string;
}

export interface ChangeRequest {
  id: number;
  title: string;
  description: string;
  project: Project;
  author: User;
  status: 'pending' | 'approved' | 'changes_requested' | 'rejected';
  change_type: 'feature' | 'bug_fix' | 'enhancement' | 'documentation' | 'refactor' | 'other';
  diff_summary?: any;
  approvals_required: number;
  approvals: Approval[];
  approval_count: number;
  is_approved: boolean;
  target_branch: string;
  created_at: string;
  updated_at: string;
}

export interface Discussion {
  id: number;
  title: string;
  content: string;
  author: User;
  category: string;
  replies: number;
  views: number;
  is_pinned: boolean;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
  last_activity: string;
}

export interface DiscussionReply {
  id: number;
  discussion: number;
  author: User;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface MarketplaceCategory {
  id: string;
  label: string;
  icon: string;
  description: string;
  order: number;
}

export interface MarketplaceItem {
  id: number;
  name: string;
  description: string;
  emoji: string;
  author: User;
  category: string;
  likes: number;
  status: string;
  gradient: string;
  tags: string[];
  demo_url: string;
  documentation_url: string;
  is_featured: boolean;
  downloads: number;
  created_at: string;
  updated_at: string;
}

// Git operations interfaces
export interface GitBranch {
  name: string;
  fullName: string;
  isRemote: boolean;
  isCurrent: boolean;
  upstream?: string;
}

export interface GitCommit {
  hash: string;
  shortHash: string;
  message: string;
  author: string;
  date: string;
  timestamp: string;
}

export interface GitRemoteStatus {
  currentBranch: string;
  trackingBranch: string;
  aheadCount: number;
  behindCount: number;
  aheadCommits: Array<{ hash: string; message: string }>;
  behindCommits: Array<{ hash: string; message: string }>;
  needsPull: boolean;
  needsPush: boolean;
}

export interface GitOperationResult {
  success: boolean;
  message?: string;
  error?: string;
  output?: string;
}

// Chatbot Interfaces
export interface ChatbotPersona {
  id: number;
  name: string;
  description: string;
  icon: string;
  category: string;
  system_prompt: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  default_llm_id?: string | null;
  default_temperature?: number;
  default_max_tokens?: number;
}

export interface ChatbotTemplate {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  user_prompt_template: string;
  variables: Array<{
    name: string;
    defaultValue: string;
    description: string;
  }>;
  category: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatSession {
  id: number;
  project?: number;
  user: number;
  persona?: number;
  persona_name?: string;
  template?: number;
  template_name?: string;
  title: string;
  llm_id?: string;
  temperature?: number;
  started_by_persona?: boolean;
  subject?: string;
  is_active: boolean;
  mode: ChatMode;
  enabled_tools?: ProjectTool[];
  enabled_tool_ids?: number[];
  message_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  session: number;
  message_type: 'user' | 'assistant' | 'system';
  content: string;
  metadata: Record<string, any>;
  created_at: string;
  reasoning?: string;
  tool_calls?: any[];
}

// Issue Interfaces
export interface Issue {
  id: number;
  title: string;
  description: string;
  project: Project;
  author: User;
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  category: 'bug' | 'feature_request' | 'question' | 'enhancement' | 'documentation' | 'other';
  votes: number;
  views: number;
  is_bookmarked: boolean;
  assigned_to?: User;
  replies_count: number;
  created_at: string;
  updated_at: string;
  last_activity: string;
}

export interface IssueReply {
  id: number;
  issue: number;
  author: User;
  content: string;
  created_at: string;
  updated_at: string;
}

// Workflow Interfaces
export interface Workflow {
  id: number;
  name: string;
  description: string;
  project: Project;
  author: User;
  status: 'draft' | 'active' | 'paused' | 'archived';
  nodes: any[];
  edges: any[];
  settings: Record<string, any>;
  last_run?: string;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowExecution {
  id: number;
  workflow: Workflow;
  triggered_by: User;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  execution_data: Record<string, any>;
  started_at: string;
  completed_at?: string;
  error_message: string;
}

// Safety & Compliance Interfaces
export interface ComplianceCheck {
  id: number;
  name: string;
  category: string;
  severity: string;
  description: string;
  ai_prompt: string;
  is_active: boolean;
  usage_count: number;
  created_by?: User;
  created_at: string;
  updated_at: string;
}

export interface ComplianceTemplate {
  id: number;
  name: string;
  description: string;
  checks: ComplianceCheck[];
  check_count: number;
  projects_using_count: number;
  is_active: boolean;
  created_by?: User;
  created_at: string;
  updated_at: string;
}

// Get auth headers with JWT token
const getAuthHeaders = () => {
  const token = localStorage.getItem('accessToken');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

interface ApiCallOptions extends RequestInit {
  skipAuth?: boolean;
}

// Generic API call function
export const apiCall = async <T = any>(
  endpoint: string,
  options: ApiCallOptions = {}
): Promise<ApiResponse<T>> => {
  const { skipAuth = false, ...requestOptions } = options;

  const makeRequest = async (token?: string): Promise<ApiResponse<T>> => {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(skipAuth ? {} : getAuthHeaders()),
        ...requestOptions.headers,
      };

      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        headers,
        ...requestOptions,
      });

      if (response.ok) {
        const data = await response.json();
        return { data };
      } else if (response.status === 401 && !skipAuth) {
        // Token expired, try to refresh
        if (isRefreshing) {
          // Queue the request if refresh is in progress
          return new Promise<string>((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          }).then((newToken: string) => makeRequest(newToken)).catch((err) => ({ error: err.message || 'Authentication failed' }));
        }

        isRefreshing = true;

        const refreshResult = await refreshToken();
        if (refreshResult.data) {
          // Update stored token
          localStorage.setItem('accessToken', refreshResult.data.access);

          // Retry original request with new token
          processQueue(null, refreshResult.data.access);
          isRefreshing = false;
          return makeRequest(refreshResult.data.access);
        } else {
          // Refresh failed, clear tokens and redirect
          processQueue(new Error('Token refresh failed'), null);
          isRefreshing = false;
          handleAuthFailure();
          return { error: 'Authentication failed' };
        }
      } else {
        const error = await response.text();
        return { error: error || 'API call failed' };
      }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Network error' };
    }
  };

  return makeRequest();
};

// Authentication functions
export const login = async (username: string, password: string): Promise<ApiResponse<LoginResponse>> => {
  return apiCall<LoginResponse>('/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    skipAuth: true,
  });
};

export const refreshToken = async (): Promise<ApiResponse<{ access: string }>> => {
  const refresh = localStorage.getItem('refreshToken');
  if (!refresh) {
    return { error: 'No refresh token available' };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh }),
    });

    if (response.ok) {
      const data = await response.json();
      return { data };
    } else {
      const error = await response.text();
      return { error: error || 'Token refresh failed' };
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Network error' };
  }
};

// Check if user is authenticated
export const isAuthenticated = (): boolean => {
  const token = localStorage.getItem('accessToken');
  return !!token;
};

// Logout function
export const logout = (): void => {
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  // Optionally clear any other user-related data
  localStorage.removeItem('user');
};

// User profile functions
export const getCurrentUser = async (): Promise<ApiResponse<User>> => {
  return apiCall<User>('/users/me/');
};

export const updateCurrentUser = async (data: Partial<User>): Promise<ApiResponse<User>> => {
  return apiCall<User>('/users/me/', {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

// Team functions
export const getTeams = async (): Promise<ApiResponse<Team[]>> => {
  return apiCall<Team[]>('/teams/');
};

// Organization functions
export const getOrganizations = async (): Promise<ApiResponse<Organization[]>> => {
  return apiCall<Organization[]>('/organizations/');
};

export const getOrganization = async (id: number): Promise<ApiResponse<Organization>> => {
  return apiCall<Organization>(`/organizations/${id}/`);
};

export const createOrganization = async (data: {
  name: string;
  description?: string;
}): Promise<ApiResponse<Organization>> => {
  return apiCall<Organization>('/organizations/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateOrganization = async (id: number, data: Partial<Organization>): Promise<ApiResponse<Organization>> => {
  return apiCall<Organization>(`/organizations/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteOrganization = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/organizations/${id}/`, {
    method: 'DELETE',
  });
};

export const getOrganizationProjects = async (organizationId: number): Promise<ApiResponse<Project[]>> => {
  return apiCall<Project[]>(`/organizations/${organizationId}/projects/`);
};

export const addOrganizationMember = async (
  organizationId: number,
  userId: number,
  role: Exclude<OrganizationRole, 'owner'> = 'member'
): Promise<ApiResponse<OrganizationMembership>> => {
  return apiCall<OrganizationMembership>(`/organizations/${organizationId}/add_member/`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, role }),
  });
};

export const removeOrganizationMember = async (organizationId: number, userId: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/organizations/${organizationId}/remove_member/`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
};

export const getOrganizationGitConnections = async (params?: {
  organizationId?: number;
}): Promise<ApiResponse<OrganizationGitConnection[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.organizationId) {
    searchParams.append('organization', params.organizationId.toString());
  }

  const query = searchParams.toString();
  return apiCall<OrganizationGitConnection[]>(`/organization-git-connections/${query ? `?${query}` : ''}`);
};

export const createOrganizationGitConnection = async (data: {
  organization_id: number;
  name: string;
  provider_type: GitProviderType;
  auth_type: GitConnectionAuthType;
  base_url?: string;
  notes?: string;
  credential_plain?: string;
}): Promise<ApiResponse<OrganizationGitConnection>> => {
  return apiCall<OrganizationGitConnection>('/organization-git-connections/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateOrganizationGitConnection = async (
  id: number,
  data: Partial<OrganizationGitConnection> & { credential_plain?: string; organization_id?: number }
): Promise<ApiResponse<OrganizationGitConnection>> => {
  return apiCall<OrganizationGitConnection>(`/organization-git-connections/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteOrganizationGitConnection = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/organization-git-connections/${id}/`, {
    method: 'DELETE',
  });
};

export const testOrganizationGitConnection = async (
  id: number
): Promise<ApiResponse<{ status: 'unknown' | 'succeeded' | 'failed'; message: string; connection: OrganizationGitConnection }>> => {
  return apiCall(`/organization-git-connections/${id}/test_connection/`, {
    method: 'POST',
  });
};

export const getOrganizationGitConnectionRepositories = async (
  id: number,
  params?: { search?: string }
): Promise<ApiResponse<GitConnectionRepositoryList>> => {
  const searchParams = new URLSearchParams();
  if (params?.search) {
    searchParams.append('search', params.search);
  }

  const query = searchParams.toString();
  return apiCall<GitConnectionRepositoryList>(`/organization-git-connections/${id}/repositories/${query ? `?${query}` : ''}`);
};

export const getOrganizationGitConnectionBranches = async (
  id: number,
  repository: string
): Promise<ApiResponse<GitConnectionBranchList>> => {
  const searchParams = new URLSearchParams();
  searchParams.append('repository', repository);
  return apiCall<GitConnectionBranchList>(`/organization-git-connections/${id}/branches/?${searchParams.toString()}`);
};

export const getPersonalGitConnections = async (): Promise<ApiResponse<PersonalGitConnection[]>> => {
  return apiCall<PersonalGitConnection[]>('/personal-git-connections/');
};

export const createPersonalGitConnection = async (data: {
  name: string;
  provider_type: GitProviderType;
  auth_type: GitConnectionAuthType;
  base_url?: string;
  notes?: string;
  credential_plain?: string;
}): Promise<ApiResponse<PersonalGitConnection>> => {
  return apiCall<PersonalGitConnection>('/personal-git-connections/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updatePersonalGitConnection = async (
  id: number,
  data: Partial<PersonalGitConnection> & { credential_plain?: string }
): Promise<ApiResponse<PersonalGitConnection>> => {
  return apiCall<PersonalGitConnection>(`/personal-git-connections/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deletePersonalGitConnection = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/personal-git-connections/${id}/`, {
    method: 'DELETE',
  });
};

export const testPersonalGitConnection = async (
  id: number
): Promise<ApiResponse<{ status: 'unknown' | 'succeeded' | 'failed'; message: string; connection: PersonalGitConnection }>> => {
  return apiCall(`/personal-git-connections/${id}/test_connection/`, {
    method: 'POST',
  });
};

export const getPersonalGitConnectionRepositories = async (
  id: number,
  params?: { search?: string }
): Promise<ApiResponse<GitConnectionRepositoryList>> => {
  const searchParams = new URLSearchParams();
  if (params?.search) {
    searchParams.append('search', params.search);
  }

  const query = searchParams.toString();
  return apiCall<GitConnectionRepositoryList>(`/personal-git-connections/${id}/repositories/${query ? `?${query}` : ''}`);
};

export const getPersonalGitConnectionBranches = async (
  id: number,
  repository: string
): Promise<ApiResponse<GitConnectionBranchList>> => {
  const searchParams = new URLSearchParams();
  searchParams.append('repository', repository);
  return apiCall<GitConnectionBranchList>(`/personal-git-connections/${id}/branches/?${searchParams.toString()}`);
};

export const getAppSourceSettings = async (appId: number): Promise<ApiResponse<AppSourceSettings>> => {
  return apiCall<AppSourceSettings>(`/apps/${appId}/source_settings/`);
};

export const updateAppSourceSettings = async (
  appId: number,
  data: Partial<AppSourceSettings> & {
    organization_connection_id?: number | null;
    personal_connection_id?: number | null;
  }
): Promise<ApiResponse<AppSourceSettings>> => {
  return apiCall<AppSourceSettings>(`/apps/${appId}/source_settings/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const getTeam = async (id: number): Promise<ApiResponse<Team>> => {
  return apiCall<Team>(`/teams/${id}/`);
};

export const createTeam = async (data: { name: string; description: string }): Promise<ApiResponse<Team>> => {
  return apiCall<Team>('/teams/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateTeam = async (id: number, data: Partial<Team>): Promise<ApiResponse<Team>> => {
  return apiCall<Team>(`/teams/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteTeam = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/teams/${id}/`, {
    method: 'DELETE',
  });
};

export const addTeamMember = async (teamId: number, userId: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/teams/${teamId}/add_member/`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
};

export const removeTeamMember = async (teamId: number, userId: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/teams/${teamId}/remove_member/`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
};

// Project functions
export const getProjects = async (): Promise<ApiResponse<Project[]>> => {
  return apiCall<Project[]>('/projects/');
};

export const getEnvironments = async (projectId?: number): Promise<ApiResponse<ProjectEnvironment[]>> => {
  const query = projectId ? `?project=${projectId}` : '';
  return apiCall<ProjectEnvironment[]>(`/environments/${query}`);
};

export const createEnvironment = async (data: {
  project_id: number;
  name: string;
  description?: string;
  environment_type?: ProjectEnvironment['environment_type'];
  workspace_image?: ProjectEnvironment['workspace_image'];
  workspace_size?: string;
  workspace_mode?: ProjectEnvironment['workspace_mode'];
  domain?: string;
  is_primary?: boolean;
}): Promise<ApiResponse<ProjectEnvironment>> => {
  return apiCall<ProjectEnvironment>('/environments/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateEnvironment = async (id: number, data: Partial<ProjectEnvironment>): Promise<ApiResponse<ProjectEnvironment>> => {
  return apiCall<ProjectEnvironment>(`/environments/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteEnvironment = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/environments/${id}/`, {
    method: 'DELETE',
  });
};

export const getApps = async (environmentId?: number): Promise<ApiResponse<ProjectApp[]>> => {
  const query = environmentId ? `?environment=${environmentId}` : '';
  return apiCall<ProjectApp[]>(`/apps/${query}`);
};

export const createApp = async (data: {
  environment_id: number;
  name: string;
  description?: string;
  source_type?: ProjectApp['source_type'];
  repository_url?: string;
  compose_path?: string;
  status?: ProjectApp['status'];
  config?: Record<string, any>;
}): Promise<ApiResponse<ProjectApp>> => {
  return apiCall<ProjectApp>('/apps/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateApp = async (id: number, data: Partial<ProjectApp>): Promise<ApiResponse<ProjectApp>> => {
  return apiCall<ProjectApp>(`/apps/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteApp = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/apps/${id}/`, {
    method: 'DELETE',
  });
};

export const getDeployments = async (params?: {
  environmentId?: number;
  appId?: number;
}): Promise<ApiResponse<DeploymentRecord[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.environmentId) {
    searchParams.set('environment', String(params.environmentId));
  }
  if (params?.appId) {
    searchParams.set('app', String(params.appId));
  }
  const query = searchParams.toString();
  const response = await apiCall<DeploymentRecord[] | PaginatedApiListResponse<DeploymentRecord>>(
    `/deployments/${query ? `?${query}` : ''}`
  );

  return {
    data: normalizeApiList<DeploymentRecord>(response.data),
    error: response.error,
  };
};

export const createDeployment = async (data: {
  app_id: number;
  version: string;
  status?: DeploymentRecord['status'];
  trigger_type?: DeploymentRecord['trigger_type'];
  source_ref?: string;
  compose_path?: string;
  notes?: string;
  config_snapshot?: Record<string, any>;
  service_snapshot?: Record<string, any>;
}): Promise<ApiResponse<DeploymentRecord>> => {
  return apiCall<DeploymentRecord>('/deployments/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateDeployment = async (id: number, data: Partial<DeploymentRecord>): Promise<ApiResponse<DeploymentRecord>> => {
  return apiCall<DeploymentRecord>(`/deployments/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteDeployment = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/deployments/${id}/`, {
    method: 'DELETE',
  });
};

export const rollbackDeployment = async (deploymentId: number, notes?: string): Promise<ApiResponse<DeploymentRecord>> => {
  return apiCall<DeploymentRecord>(`/deployments/${deploymentId}/rollback/`, {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
};

export const ensureProjectPod = async (projectId: number): Promise<ApiResponse<ProjectPod>> => {
  return apiCall<ProjectPod>('/project-pods/ensure/', {
    method: 'POST',
    body: JSON.stringify({ project: projectId }),
  });
};

export const getProjectServices = async (
  projectId: number,
  serviceTypeOrOptions?: string | { serviceType?: string; appId?: number }
): Promise<ApiResponse<ProjectService[]>> => {
  const serviceType = typeof serviceTypeOrOptions === 'string'
    ? serviceTypeOrOptions
    : serviceTypeOrOptions?.serviceType;
  const appId = typeof serviceTypeOrOptions === 'string'
    ? undefined
    : serviceTypeOrOptions?.appId;
  const searchParams = new URLSearchParams({ project: String(projectId) });

  if (serviceType) {
    searchParams.set('service_type', serviceType);
  }

  if (appId !== undefined) {
    searchParams.set('app', String(appId));
  }

  return apiCall<ProjectService[]>(`/project-services/?${searchParams.toString()}`);
};

export const createProjectService = async (data: {
  app: number;
  name: string;
  service_type?: ProjectService['service_type'];
  image: string;
  container_name?: string;
  ports?: string[];
  environment?: Record<string, string>;
  config?: Record<string, any>;
  autostart?: boolean;
  cpu_limit?: string;
  memory_limit?: string;
}): Promise<ApiResponse<ProjectService>> => {
  return apiCall<ProjectService>('/project-services/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateProjectServiceRecord = async (id: number, data: Partial<ProjectService>): Promise<ApiResponse<ProjectService>> => {
  return apiCall<ProjectService>(`/project-services/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteProjectServiceRecord = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/project-services/${id}/`, {
    method: 'DELETE',
  });
};

export const stopWorkspace = async (projectId: number): Promise<ApiResponse<{ status: string; message: string }>> => {
  return apiCall(`/projects/${projectId}/stop_workspace/`, {
    method: 'POST',
  });
};

export const restartWorkspace = async (projectId: number): Promise<ApiResponse<{ status: string; message: string }>> => {
  return apiCall(`/projects/${projectId}/restart_workspace/`, {
    method: 'POST',
  });
};

export const deleteService = async (projectId: number, serviceId: number): Promise<ApiResponse<{ status: string; message: string }>> => {
  return apiCall(`/projects/${projectId}/delete_service/`, {
    method: 'POST',
    body: JSON.stringify({ service_id: serviceId }),
  });
};

export const startAllServices = async (projectId: number): Promise<ApiResponse<{ status: string; started: string[]; errors: any[] }>> => {
  return apiCall(`/projects/${projectId}/start_all_services/`, {
    method: 'POST',
  });
};

export const stopAllServices = async (projectId: number): Promise<ApiResponse<{ status: string; stopped: string[]; errors: any[] }>> => {
  return apiCall(`/projects/${projectId}/stop_all_services/`, {
    method: 'POST',
  });
};

export const provisionServices = async (projectId: number): Promise<ApiResponse<{ status: string; message: string }>> => {
  return apiCall(`/projects/${projectId}/provision_services/`, {
    method: 'POST',
  });
};

export const startService = async (projectId: number, serviceId: number): Promise<ApiResponse<{ status: string; message: string }>> => {
  return apiCall(`/projects/${projectId}/start_service/`, {
    method: 'POST',
    body: JSON.stringify({ service_id: serviceId }),
  });
};

export const restartService = async (serviceId: number): Promise<ApiResponse<{ status: string }>> => {
  return apiCall(`/project-services/${serviceId}/restart/`, {
    method: 'POST',
  });
};

export const stopService = async (serviceId: number): Promise<ApiResponse<{ status: string }>> => {
  return apiCall(`/project-services/${serviceId}/stop/`, {
    method: 'POST',
  });
};

export const killService = async (serviceId: number): Promise<ApiResponse<{ status: string }>> => {
  return apiCall(`/project-services/${serviceId}/kill/`, {
    method: 'POST',
  });
};

export const getProjectTools = async (projectId: number): Promise<ApiResponse<ProjectTool[]>> => {
  return apiCall<ProjectTool[]>(`/project-tools/?project=${projectId}`);
};

export const createProjectTool = async (data: Partial<ProjectTool>): Promise<ApiResponse<ProjectTool>> => {
  return apiCall<ProjectTool>('/project-tools/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const executeProjectTool = async (
  toolId: number,
  argumentsPayload?: Record<string, any>
): Promise<ApiResponse<{ output: Record<string, any> }>> => {
  return apiCall(`/project-tools/${toolId}/execute/`, {
    method: 'POST',
    body: JSON.stringify({ arguments: argumentsPayload || {} }),
  });
};

export const createProject = async (data: {
  name: string;
  description: string;
  owner: number;
  organization_id?: number;
  team?: number;
  contributors?: number[];
  creation_method?: 'blank' | 'clone' | 'chat' | 'template';
  git_repo_url?: string;
  branch?: string;
  template?: number;
  workspace_image?: string;
  workspace_size?: string;
}): Promise<ApiResponse<Project>> => {
  return apiCall<Project>('/projects/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getProjectProvisioningStatus = async (projectId: number): Promise<ApiResponse<{
  status: string;
  creation_method: string;
  git_repo_url: string;
  branch: string;
}>> => {
  return apiCall(`/projects/${projectId}/provisioning_status/`, {
    method: 'GET',
  });
};

export const updateProject = async (id: number, data: Partial<Project>): Promise<ApiResponse<Project>> => {
  return apiCall<Project>(`/projects/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteProject = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/projects/${id}/`, {
    method: 'DELETE',
  });
};

// Project Template functions
export const getProjectTemplates = async (): Promise<ApiResponse<ProjectTemplate[]>> => {
  return apiCall<ProjectTemplate[]>('/project-templates/');
};

export const createProjectTemplate = async (data: {
  name: string;
  description: string;
  language: string;
  framework: string;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  tags?: string[];
}): Promise<ApiResponse<ProjectTemplate>> => {
  return apiCall<ProjectTemplate>('/project-templates/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateProjectTemplate = async (id: number, data: Partial<ProjectTemplate>): Promise<ApiResponse<ProjectTemplate>> => {
  return apiCall<ProjectTemplate>(`/project-templates/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteProjectTemplate = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/project-templates/${id}/`, {
    method: 'DELETE',
  });
};

export const getMyProjects = async (): Promise<ApiResponse<Project[]>> => {
  return apiCall<Project[]>('/projects/my_projects/');
};

// ChangeRequest functions
export const getChangeRequests = async (): Promise<ApiResponse<ChangeRequest[]>> => {
  return apiCall<ChangeRequest[]>('/change-requests/');
};

export const createChangeRequest = async (data: {
  title: string;
  description: string;
  project: number;
  change_type?: string;
  diff_summary?: any;
  target_branch?: string;
}): Promise<ApiResponse<ChangeRequest>> => {
  return apiCall<ChangeRequest>('/change-requests/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateChangeRequest = async (id: number, data: Partial<ChangeRequest>): Promise<ApiResponse<ChangeRequest>> => {
  return apiCall<ChangeRequest>(`/change-requests/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteChangeRequest = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/change-requests/${id}/`, {
    method: 'DELETE',
  });
};

export const approveChangeRequest = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/change-requests/${id}/approve/`, {
    method: 'POST',
  });
};

export const requestChangesChangeRequest = async (id: number, comments?: string): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/change-requests/${id}/request_changes/`, {
    method: 'POST',
    body: JSON.stringify({ comments }),
  });
};

// Discussion functions
export const getDiscussions = async (): Promise<ApiResponse<Discussion[]>> => {
  return apiCall<Discussion[]>('/discussions/');
};

export const getDiscussion = async (id: number): Promise<ApiResponse<Discussion>> => {
  return apiCall<Discussion>(`/discussions/${id}/`);
};

export const createDiscussion = async (data: { title: string; content: string; category?: string }): Promise<ApiResponse<Discussion>> => {
  return apiCall<Discussion>('/discussions/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateDiscussion = async (id: number, data: Partial<Discussion>): Promise<ApiResponse<Discussion>> => {
  return apiCall<Discussion>(`/discussions/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteDiscussion = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/discussions/${id}/`, {
    method: 'DELETE',
  });
};

export const incrementDiscussionViews = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/discussions/${id}/increment-views/`, {
    method: 'POST',
  });
};

export const toggleDiscussionPin = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/discussions/${id}/toggle-pin/`, {
    method: 'POST',
  });
};

export const toggleDiscussionLock = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/discussions/${id}/toggle-lock/`, {
    method: 'POST',
  });
};

// Marketplace functions
export const getMarketplaceCategories = async (): Promise<ApiResponse<MarketplaceCategory[]>> => {
  return apiCall<MarketplaceCategory[]>('/marketplace-categories/');
};

export const getMarketplaceItems = async (params?: {
  category?: string;
  search?: string;
  featured?: boolean;
}): Promise<ApiResponse<MarketplaceItem[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.category && params.category !== 'all') {
    searchParams.append('category', params.category);
  }
  if (params?.search) {
    searchParams.append('search', params.search);
  }
  if (params?.featured) {
    searchParams.append('featured', 'true');
  }

  const url = searchParams.toString()
    ? `/marketplace-items/?${searchParams.toString()}`
    : '/marketplace-items/';

  return apiCall<MarketplaceItem[]>(url);
};

export const getMarketplaceItem = async (id: number): Promise<ApiResponse<MarketplaceItem>> => {
  return apiCall<MarketplaceItem>(`/marketplace-items/${id}/`);
};

export const createMarketplaceItem = async (data: {
  name: string;
  description: string;
  emoji?: string;
  category: string;
  gradient?: string;
  tags?: string[];
  demo_url?: string;
  documentation_url?: string;
}): Promise<ApiResponse<MarketplaceItem>> => {
  return apiCall<MarketplaceItem>('/marketplace-items/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateMarketplaceItem = async (id: number, data: Partial<MarketplaceItem>): Promise<ApiResponse<MarketplaceItem>> => {
  return apiCall<MarketplaceItem>(`/marketplace-items/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteMarketplaceItem = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/marketplace-items/${id}/`, {
    method: 'DELETE',
  });
};

export const likeMarketplaceItem = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/marketplace-items/${id}/like/`, {
    method: 'POST',
  });
};

export const incrementMarketplaceItemDownloads = async (id: number): Promise<ApiResponse<any>> => {
  return apiCall<any>(`/marketplace-items/${id}/increment_downloads/`, {
    method: 'POST',
  });
};

// Discussion Reply functions
export const getDiscussionReplies = async (discussionId?: number): Promise<ApiResponse<DiscussionReply[]>> => {
  const url = discussionId ? `/discussion-replies/?discussion=${discussionId}` : '/discussion-replies/';
  return apiCall<DiscussionReply[]>(url);
};

export const createDiscussionReply = async (data: { discussion: number; content: string }): Promise<ApiResponse<DiscussionReply>> => {
  return apiCall<DiscussionReply>('/discussion-replies/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateDiscussionReply = async (id: number, data: Partial<DiscussionReply>): Promise<ApiResponse<DiscussionReply>> => {
  return apiCall<DiscussionReply>(`/discussion-replies/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteDiscussionReply = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/discussion-replies/${id}/`, {
    method: 'DELETE',
  });
};

// Chatbot functions
export const getChatbotPersonas = async (params?: {
  category?: string;
}): Promise<ApiResponse<ChatbotPersona[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.category) {
    searchParams.append('category', params.category);
  }

  const url = searchParams.toString()
    ? `/chatbot-personas/?${searchParams.toString()}`
    : '/chatbot-personas/';

  return apiCall<ChatbotPersona[]>(url);
};

export const getChatbotPersona = async (id: number): Promise<ApiResponse<ChatbotPersona>> => {
  return apiCall<ChatbotPersona>(`/chatbot-personas/${id}/`);
};

export const createChatbotPersona = async (data: {
  name: string;
  description: string;
  icon?: string;
  category?: string;
  system_prompt?: string;
}): Promise<ApiResponse<ChatbotPersona>> => {
  return apiCall<ChatbotPersona>('/chatbot-personas/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateChatbotPersona = async (id: number, data: Partial<ChatbotPersona>): Promise<ApiResponse<ChatbotPersona>> => {
  return apiCall<ChatbotPersona>(`/chatbot-personas/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteChatbotPersona = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/chatbot-personas/${id}/`, {
    method: 'DELETE',
  });
};

export const getChatbotTemplates = async (params?: {
  category?: string;
}): Promise<ApiResponse<ChatbotTemplate[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.category) {
    searchParams.append('category', params.category);
  }

  const url = searchParams.toString()
    ? `/chatbot-templates/?${searchParams.toString()}`
    : '/chatbot-templates/';

  return apiCall<ChatbotTemplate[]>(url);
};

export const getChatbotTemplate = async (id: number): Promise<ApiResponse<ChatbotTemplate>> => {
  return apiCall<ChatbotTemplate>(`/chatbot-templates/${id}/`);
};

export const createChatbotTemplate = async (data: {
  name: string;
  description: string;
  system_prompt: string;
  user_prompt_template: string;
  variables?: Array<{
    name: string;
    defaultValue: string;
    description: string;
  }>;
  category?: string;
}): Promise<ApiResponse<ChatbotTemplate>> => {
  return apiCall<ChatbotTemplate>('/chatbot-templates/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateChatbotTemplate = async (id: number, data: Partial<ChatbotTemplate>): Promise<ApiResponse<ChatbotTemplate>> => {
  return apiCall<ChatbotTemplate>(`/chatbot-templates/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteChatbotTemplate = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/chatbot-templates/${id}/`, {
    method: 'DELETE',
  });
};

export const getChatSessions = async (projectId?: number): Promise<ApiResponse<ChatSession[]>> => {
  let url = '/chat-sessions/';
  if (projectId) {
    url += `?project=${projectId}`;
  }
  return apiCall<ChatSession[]>(url);
};

export const getChatSession = async (id: number): Promise<ApiResponse<ChatSession>> => {
  return apiCall<ChatSession>(`/chat-sessions/${id}/`);
};

export const createChatSession = async (data: {
  project?: number;
  persona?: number;
  template?: number;
  title?: string;
  llm_id?: string;
  temperature?: number;
  started_by_persona?: boolean;
  mode?: ChatMode;
  enabled_tool_ids?: number[];
}): Promise<ApiResponse<ChatSession>> => {
  return apiCall<ChatSession>('/chat-sessions/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateChatSession = async (id: number, data: Partial<ChatSession>): Promise<ApiResponse<ChatSession>> => {
  return apiCall<ChatSession>(`/chat-sessions/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteChatSession = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/chat-sessions/${id}/`, {
    method: 'DELETE',
  });
};

export const sendChatMessage = async (
  sessionId: number, 
  message: string, 
  llmId?: string, 
  temperature?: number,
  options?: {
    mode?: ChatMode;
    personaId?: number | null;
    enabledTools?: number[];
  }
): Promise<ApiResponse<{ user_message: ChatMessage; ai_message: ChatMessage }>> => {
  const body: any = { message };
  if (llmId) body.llm_id = llmId;
  if (temperature !== undefined) body.temperature = temperature;
  if (options?.mode) body.mode = options.mode;
  if (options && 'personaId' in options) body.persona = options.personaId;
  if (options && 'enabledTools' in options) body.enabled_tools = options.enabledTools;
  
  return apiCall<{ user_message: ChatMessage; ai_message: ChatMessage }>(`/chat-sessions/${sessionId}/send_message/`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const summarizeConversation = async (sessionId: number): Promise<ApiResponse<{ subject: string }>> => {
  return apiCall<{ subject: string }>(`/chat-sessions/${sessionId}/summarize/`, {
    method: 'POST',
  });
};

export const getChatMessages = async (sessionId: number): Promise<ApiResponse<ChatMessage[]>> => {
  return apiCall<ChatMessage[]>(`/chat-messages/?session=${sessionId}`);
};

export const updateChatMessage = async (messageId: number, content: string, clearAfter?: boolean): Promise<ApiResponse<ChatMessage>> => {
  return apiCall<ChatMessage>(`/chat-messages/${messageId}/`, {
    method: 'PATCH',
    body: JSON.stringify({
      content,
      clear_after: clearAfter,
    }),
  });
};

export const getAvailableLLMs = async (): Promise<ApiResponse<LLMConfigResponse>> => {
  return apiCall<LLMConfigResponse>('/llm-config/available_llms/');
};

// LLM Configuration functions
export interface LLMConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  description: string;
  max_tokens: number;
  temperature: number;
  available: boolean;
}

export interface LLMConfigResponse {
  llms: LLMConfig[];
  default_llm: string;
}

// Safety & Compliance functions
export const getComplianceChecks = async (params?: {
  category?: string;
  search?: string;
}): Promise<ApiResponse<ComplianceCheck[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.category && params.category !== 'all') {
    searchParams.append('category', params.category);
  }
  if (params?.search) {
    searchParams.append('search', params.search);
  }

  const url = searchParams.toString()
    ? `/compliance-checks/?${searchParams.toString()}`
    : '/compliance-checks/';

  return apiCall<ComplianceCheck[]>(url);
};

export const getComplianceCheck = async (id: number): Promise<ApiResponse<ComplianceCheck>> => {
  return apiCall<ComplianceCheck>(`/compliance-checks/${id}/`);
};

export const createComplianceCheck = async (data: {
  name: string;
  category: string;
  severity: string;
  description: string;
  ai_prompt: string;
}): Promise<ApiResponse<ComplianceCheck>> => {
  return apiCall<ComplianceCheck>('/compliance-checks/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateComplianceCheck = async (id: number, data: Partial<ComplianceCheck>): Promise<ApiResponse<ComplianceCheck>> => {
  return apiCall<ComplianceCheck>(`/compliance-checks/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteComplianceCheck = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/compliance-checks/${id}/`, {
    method: 'DELETE',
  });
};

export const getComplianceTemplates = async (params?: {
  search?: string;
}): Promise<ApiResponse<ComplianceTemplate[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.search) {
    searchParams.append('search', params.search);
  }

  const url = searchParams.toString()
    ? `/compliance-templates/?${searchParams.toString()}`
    : '/compliance-templates/';

  return apiCall<ComplianceTemplate[]>(url);
};

export const getComplianceTemplate = async (id: number): Promise<ApiResponse<ComplianceTemplate>> => {
  return apiCall<ComplianceTemplate>(`/compliance-templates/${id}/`);
};

export const createComplianceTemplate = async (data: {
  name: string;
  description: string;
  checks: number[];
}): Promise<ApiResponse<ComplianceTemplate>> => {
  return apiCall<ComplianceTemplate>('/compliance-templates/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateComplianceTemplate = async (id: number, data: Partial<ComplianceTemplate>): Promise<ApiResponse<ComplianceTemplate>> => {
  return apiCall<ComplianceTemplate>(`/compliance-templates/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteComplianceTemplate = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/compliance-templates/${id}/`, {
    method: 'DELETE',
  });
};

// Project Assignment functions
export interface ProjectAssignment {
  id: number;
  project: Project;
  template?: ComplianceTemplate;
  custom_checks: ComplianceCheck[];
  last_run?: string;
  status: string;
  violations: number;
}

export const getProjectAssignments = async (): Promise<ApiResponse<ProjectAssignment[]>> => {
  return apiCall<ProjectAssignment[]>('/project-assignments/');
};

export const getProjectAssignment = async (id: number): Promise<ApiResponse<ProjectAssignment>> => {
  return apiCall<ProjectAssignment>(`/project-assignments/${id}/`);
};

export const createProjectAssignment = async (data: {
  project: number;
  template?: number;
  custom_checks?: number[];
}): Promise<ApiResponse<ProjectAssignment>> => {
  return apiCall<ProjectAssignment>('/project-assignments/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateProjectAssignment = async (id: number, data: Partial<ProjectAssignment>): Promise<ApiResponse<ProjectAssignment>> => {
  return apiCall<ProjectAssignment>(`/project-assignments/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteProjectAssignment = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/project-assignments/${id}/`, {
    method: 'DELETE',
  });
};

// Issue functions
export const getIssues = async (params?: {
  project?: number;
  search?: string;
  status?: string;
  category?: string;
}): Promise<ApiResponse<Issue[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.project) {
    searchParams.append('project', params.project.toString());
  }
  if (params?.search) {
    searchParams.append('search', params.search);
  }
  if (params?.status) {
    searchParams.append('status', params.status);
  }
  if (params?.category) {
    searchParams.append('category', params.category);
  }

  const url = searchParams.toString()
    ? `/issues/?${searchParams.toString()}`
    : '/issues/';

  return apiCall<Issue[]>(url);
};

export const getIssue = async (id: number): Promise<ApiResponse<Issue>> => {
  return apiCall<Issue>(`/issues/${id}/`);
};

export const createIssue = async (data: {
  title: string;
  description: string;
  project: number;
  category?: string;
  assigned_to?: number;
}): Promise<ApiResponse<Issue>> => {
  return apiCall<Issue>('/issues/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateIssue = async (id: number, data: Partial<Issue>): Promise<ApiResponse<Issue>> => {
  return apiCall<Issue>(`/issues/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteIssue = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/issues/${id}/`, {
    method: 'DELETE',
  });
};

export const voteIssue = async (id: number): Promise<ApiResponse<{ votes: number }>> => {
  return apiCall<{ votes: number }>(`/issues/${id}/vote/`, {
    method: 'POST',
  });
};

export const bookmarkIssue = async (id: number): Promise<ApiResponse<{ is_bookmarked: boolean }>> => {
  return apiCall<{ is_bookmarked: boolean }>(`/issues/${id}/bookmark/`, {
    method: 'POST',
  });
};

export const viewIssue = async (id: number): Promise<ApiResponse<{ views: number }>> => {
  return apiCall<{ views: number }>(`/issues/${id}/view/`, {
    method: 'POST',
  });
};

// Issue Reply functions
export const getIssueReplies = async (issueId: number): Promise<ApiResponse<IssueReply[]>> => {
  return apiCall<IssueReply[]>(`/issue-replies/?issue=${issueId}`);
};

export const createIssueReply = async (data: {
  issue: number;
  content: string;
}): Promise<ApiResponse<IssueReply>> => {
  return apiCall<IssueReply>('/issue-replies/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateIssueReply = async (id: number, data: Partial<IssueReply>): Promise<ApiResponse<IssueReply>> => {
  return apiCall<IssueReply>(`/issue-replies/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteIssueReply = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/issue-replies/${id}/`, {
    method: 'DELETE',
  });
};

// Workflow functions
export const getWorkflows = async (params?: {
  project?: number;
  search?: string;
  status?: string;
}): Promise<ApiResponse<Workflow[]>> => {
  const searchParams = new URLSearchParams();
  if (params?.project) {
    searchParams.append('project', params.project.toString());
  }
  if (params?.search) {
    searchParams.append('search', params.search);
  }
  if (params?.status) {
    searchParams.append('status', params.status);
  }

  const url = searchParams.toString()
    ? `/workflows/?${searchParams.toString()}`
    : '/workflows/';

  return apiCall<Workflow[]>(url);
};

export const getWorkflow = async (id: number): Promise<ApiResponse<Workflow>> => {
  return apiCall<Workflow>(`/workflows/${id}/`);
};

export const createWorkflow = async (data: {
  name: string;
  description: string;
  project: number;
  nodes?: any[];
  edges?: any[];
  settings?: Record<string, any>;
}): Promise<ApiResponse<Workflow>> => {
  return apiCall<Workflow>('/workflows/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateWorkflow = async (id: number, data: Partial<Workflow>): Promise<ApiResponse<Workflow>> => {
  return apiCall<Workflow>(`/workflows/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteWorkflow = async (id: number): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/workflows/${id}/`, {
    method: 'DELETE',
  });
};

export const executeWorkflow = async (id: number): Promise<ApiResponse<WorkflowExecution>> => {
  return apiCall<WorkflowExecution>(`/workflows/${id}/execute/`, {
    method: 'POST',
  });
};

// Workflow Execution functions
export const getWorkflowExecutions = async (workflowId?: number): Promise<ApiResponse<WorkflowExecution[]>> => {
  const url = workflowId ? `/workflow-executions/?workflow=${workflowId}` : '/workflow-executions/';
  return apiCall<WorkflowExecution[]>(url);
};

export const getWorkflowExecution = async (id: number): Promise<ApiResponse<WorkflowExecution>> => {
  return apiCall<WorkflowExecution>(`/workflow-executions/${id}/`);
};

// Webtop and Container Management functions
export interface WebtopEnsureResponse {
  status: string;
  service: {
    name: string;
    container_name: string;
    status: string;
    started_at?: string;
    proxy_url: string;
  };
  workspace_volume: string;
}

export interface ServiceActionResponse {
  status: string;
  service: {
    name: string;
    container_name: string;
    status: string;
    started_at?: string;
  };
}

export interface ServiceLogsResponse {
  status: string;
  logs: string;
  truncated: boolean;
  service: {
    name: string;
    container_name: string;
  };
}

export const ensureWebtop = async (projectId: number): Promise<ApiResponse<WebtopEnsureResponse>> => {
  return apiCall<WebtopEnsureResponse>(`/projects/${projectId}/ensure_webtop/`, {
    method: 'POST',
  });
};

export const getServiceLogs = async (
  serviceId: number, 
  params?: { tail?: number; since?: string }
): Promise<ApiResponse<ServiceLogsResponse>> => {
  const queryParams = new URLSearchParams();
  if (params?.tail) queryParams.append('tail', params.tail.toString());
  if (params?.since) queryParams.append('since', params.since);
  
  const url = `/project-services/${serviceId}/logs/?${queryParams.toString()}`;
  return apiCall<ServiceLogsResponse>(url);
};

export const getWebtopProxyUrl = (projectId: number): string => {
  const token = localStorage.getItem('accessToken');
  const baseUrl = `${API_BASE_URL}/projects/${projectId}/webtop-proxy/`;
  return token ? `${baseUrl}?token=${token}` : baseUrl;
};

/**
 * Get the subdomain-based URL for a service proxy.
 * Uses pattern: http://proj-{projectId}-{serviceId}-{port}.localhost:8000/
 * The auth flow will redirect to set a cookie, then redirect back.
 */
export const getServiceProxyUrl = (projectId: number, serviceId: number, port: string): string => {
  // Use subdomain-based URL for SPAs to work correctly
  return `http://proj-${projectId}-${serviceId}-${port}.localhost:8000/`;
};

/**
 * Get the auth URL that sets the cookie and redirects to the subdomain.
 * Use this as the initial iframe src to authenticate before loading the app.
 */
export const getServiceProxyAuthUrl = (projectId: number, serviceId: number, port: string): string => {
  const token = localStorage.getItem('accessToken');
  if (!token) {
    return getServiceProxyUrl(projectId, serviceId, port);
  }
  
  const redirectUrl = getServiceProxyUrl(projectId, serviceId, port);
  const authUrl = `${API_BASE_URL}/service-proxy-auth/`;
  const params = new URLSearchParams({
    token,
    project_id: String(projectId),
    service_id: String(serviceId),
    port: port,
    redirect: redirectUrl,
  });
  
  return `${authUrl}?${params.toString()}`;
};

// Workspace Resource Tier interfaces and functions
export interface WorkspaceResourceTier {
  id: number;
  name: string;
  slug: string;
  cpu_limit: string;
  memory_limit: string;
  display_name: string;
  is_default: boolean;
  is_active: boolean;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceEnsureResponse {
  status: string;
  service: {
    name: string;
    container_name: string;
    status: string;
    started_at?: string;
  };
  workspace_config: {
    image: string;
    size: string;
    mode: string;
  };
}

export interface WorkspaceUpdateResponse {
  status: string;
  message: string;
  service: {
    container_name: string;
    status: string;
  };
}

export interface WorkspaceResetResponse {
  status: string;
  message: string;
}

export const getWorkspaceTiers = async (): Promise<ApiResponse<WorkspaceResourceTier[]>> => {
  return apiCall<WorkspaceResourceTier[]>('/workspace-tiers/');
};

export const getWorkspaceTier = async (slug: string): Promise<ApiResponse<WorkspaceResourceTier>> => {
  return apiCall<WorkspaceResourceTier>(`/workspace-tiers/${slug}/`);
};

export const createWorkspaceTier = async (data: Partial<WorkspaceResourceTier>): Promise<ApiResponse<WorkspaceResourceTier>> => {
  return apiCall<WorkspaceResourceTier>('/workspace-tiers/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateWorkspaceTier = async (slug: string, data: Partial<WorkspaceResourceTier>): Promise<ApiResponse<WorkspaceResourceTier>> => {
  return apiCall<WorkspaceResourceTier>(`/workspace-tiers/${slug}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteWorkspaceTier = async (slug: string): Promise<ApiResponse<null>> => {
  return apiCall<null>(`/workspace-tiers/${slug}/`, {
    method: 'DELETE',
  });
};

export const ensureWorkspace = async (projectId: number): Promise<ApiResponse<WorkspaceEnsureResponse>> => {
  return apiCall<WorkspaceEnsureResponse>(`/projects/${projectId}/ensure_workspace/`, {
    method: 'POST',
  });
};

export const updateWorkspaceImage = async (projectId: number): Promise<ApiResponse<WorkspaceUpdateResponse>> => {
  return apiCall<WorkspaceUpdateResponse>(`/projects/${projectId}/update_workspace_image/`, {
    method: 'POST',
  });
};

export const resetWorkspace = async (projectId: number): Promise<ApiResponse<WorkspaceResetResponse>> => {
  return apiCall<WorkspaceResetResponse>(`/projects/${projectId}/reset_workspace/`, {
    method: 'POST',
  });
};

// Workspace File System API

export interface FileNode {
  name: string;
  type: 'file' | 'folder';
  path: string;
  children?: FileNode[];
}

export interface FileTreeResponse {
  success: boolean;
  tree: FileNode;
  timestamp: string;
}

export interface FileReadResponse {
  success: boolean;
  path: string;
  content: string;
}

export interface FileWriteResponse {
  success: boolean;
  path: string;
  message: string;
}

export interface FileDeleteResponse {
  success: boolean;
  path: string;
  message: string;
}

/**
 * Get complete file tree of workspace
 */
export const getWorkspaceFileTree = async (projectId: number): Promise<ApiResponse<FileTreeResponse>> => {
  return apiCall<FileTreeResponse>(`/projects/${projectId}/workspace/files/tree/`);
};

/**
 * Read file content from workspace
 */
export const readWorkspaceFile = async (projectId: number, filepath: string): Promise<ApiResponse<FileReadResponse>> => {
  return apiCall<FileReadResponse>(`/projects/${projectId}/workspace/files/read/${filepath}`);
};

/**
 * Create new file in workspace
 */
export const createWorkspaceFile = async (
  projectId: number,
  path: string,
  content: string
): Promise<ApiResponse<FileWriteResponse>> => {
  return apiCall<FileWriteResponse>(`/projects/${projectId}/workspace/files/create/`, {
    method: 'POST',
    body: JSON.stringify({ path, content }),
  });
};

/**
 * Update file content in workspace
 */
export const updateWorkspaceFile = async (
  projectId: number,
  filepath: string,
  content: string
): Promise<ApiResponse<FileWriteResponse>> => {
  return apiCall<FileWriteResponse>(`/projects/${projectId}/workspace/files/update/${filepath}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
};

/**
 * Delete file from workspace
 */
export const deleteWorkspaceFile = async (
  projectId: number,
  filepath: string
): Promise<ApiResponse<FileDeleteResponse>> => {
  return apiCall<FileDeleteResponse>(`/projects/${projectId}/workspace/files/delete/${filepath}`, {
    method: 'DELETE',
  });
};

/**
 * Analyze workspace file (quick or deep). If sessionId is provided and mode is 'deep',
 * the server will stream progress events to the LangGraph session WebSocket group.
 */
export const analyzeWorkspaceFile = async (
  projectId: number,
  path: string,
  mode: 'quick' | 'deep' = 'quick',
  sessionId?: number
): Promise<ApiResponse<any>> => {
  return apiCall(`/projects/${projectId}/workspace/files/analyze/`, {
    method: 'POST',
    body: JSON.stringify({ path, mode, session_id: sessionId }),
  });
};

/**
 * Get available tools for a chat session
 */
export const getSessionTools = async (
  projectId: number,
  sessionId: number
): Promise<ApiResponse<{ tools: any[] }>> => {
  return apiCall(`/projects/${projectId}/chat-sessions/${sessionId}/available_tools/`, {
    method: 'GET',
  });
};

// Streaming API for SSE responses

export interface StreamingEventMap {
  'start': { message: string; session_id: number };
  'thinking': { reasoning: string; step?: number };
  'content': { chunk: string; complete: boolean };
  'text_chunk': { content: string; chunk?: string; node?: string };
  'reasoning': { content: string; reasoning?: string };
  'tool_call': { tool: string; args: Record<string, any>; step?: number };
  'tool_start': { name: string; args: Record<string, any> | string; run_id?: string };
  'tool_result': { name: string; output: string; duration?: number; run_id?: string };
  'worker_start': { worker: string };
  'worker_end': { worker: string; content?: string };
  'todos_update': { todos: Array<{ title: string; status: string }> };
  'metadata': { reasoning?: string; artifacts?: any[]; tool_calls?: any[]; tokens_used?: number };
  'done': { status: string; session_id: number };
  'complete': { status: string; content?: string; tool_calls?: any[]; elapsed_seconds?: number; session_id?: number };
  'error': { error: string; message: string };
}

export type StreamingEventType = keyof StreamingEventMap;

/**
 * Stream chat message response using Server-Sent Events
 * Returns an EventSource that emits structured events
 */
export const sendStreamingChatMessage = (
  projectId: number,
  sessionId: number,
  message: string,
  options?: {
    llm_id?: string;
    temperature?: number;
    max_tokens?: number;
    mode?: ChatMode;
    persona_id?: number;
    enabled_tool_ids?: number[];
  }
): EventSource | null => {
  try {
    const token = localStorage.getItem('accessToken');
    const url = new URL(
      `/api/projects/${projectId}/chat-sessions/${sessionId}/stream/`,
      window.location.origin
    );
    
    // Build request body
    const body = {
      message,
      llm_id: options?.llm_id,
      temperature: options?.temperature ?? 0.7,
      max_tokens: options?.max_tokens ?? 2000,
      mode: options?.mode ?? 'ask',
      persona_id: options?.persona_id,
      enabled_tool_ids: options?.enabled_tool_ids ?? [],
    };
    
    // Note: EventSource doesn't support request body directly
    // This is a simplified approach - in production, use fetch with ReadableStream
    // For now, we'll make a POST request and handle streaming via fetch
    
    return null; // Will be handled by streaming fetch function below
  } catch (error) {
    logger.error('Error creating streaming connection:', error);
    return null;
  }
};

/**
 * Stream chat message using fetch API with manual event parsing
 * More flexible than EventSource for handling POST requests
 */
// Global abort controller for streaming requests to cancel previous ones
let streamAbortController: AbortController | null = null;
// Timeout ID for detecting hung streams
let streamTimeoutId: NodeJS.Timeout | null = null;
// Constant for stream timeout (30 seconds = 30000ms)
const STREAM_TIMEOUT_MS = 30000;

export const streamChatMessage = async (
  projectId: number,
  sessionId: number,
  message: string,
  onEvent: (type: StreamingEventType, data: any) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
  options?: {
    llm_id?: string;
    temperature?: number;
    max_tokens?: number;
    mode?: ChatMode;
    persona_id?: number;
    enabled_tool_ids?: number[];
    context_files?: Array<{ path: string; content: string }>;
  }
): Promise<void> => {
  try {
    // Clear any previous timeout
    if (streamTimeoutId) {
      clearTimeout(streamTimeoutId);
      streamTimeoutId = null;
    }
    
    // Cancel any previous streaming request
    if (streamAbortController) {
      streamAbortController.abort();
    }
    
    streamAbortController = new AbortController();
    
    // Set up timeout to auto-abort stuck streams
    streamTimeoutId = setTimeout(() => {
      logger.warn('[Stream] Timeout: No data received for 30 seconds, aborting...');
      if (streamAbortController) {
        streamAbortController.abort();
      }
    }, STREAM_TIMEOUT_MS);
    
    const token = localStorage.getItem('accessToken');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const body = JSON.stringify({
      message,
      llm_id: options?.llm_id,
      temperature: options?.temperature ?? 0.7,
      max_tokens: options?.max_tokens ?? 2000,
      mode: options?.mode ?? 'ask',
      persona_id: options?.persona_id,
      enabled_tool_ids: options?.enabled_tool_ids ?? [],
      context_files: options?.context_files ?? [],
    });
    
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/chat-sessions/${sessionId}/stream/`,
      {
        method: 'POST',
        headers,
        body,
        signal: streamAbortController.signal,
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    if (!response.body) {
      throw new Error('Response body is null');
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let eventCount = 0;
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      // Reset timeout on each chunk received (proof of life)
      if (streamTimeoutId) {
        clearTimeout(streamTimeoutId);
      }
      streamTimeoutId = setTimeout(() => {
        logger.warn('[Stream] Timeout: No data received for 30 seconds, aborting...');
        if (streamAbortController) {
          streamAbortController.abort();
        }
      }, STREAM_TIMEOUT_MS);
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      // Keep last incomplete line in buffer
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            // Emit event with its type
            if (data.type) {
              eventCount++;
              logger.debug(`[Stream] Event ${eventCount}: type=${data.type}, content=${data.content ? data.content.substring(0, 50) : 'N/A'}`);
              onEvent(data.type, data);
            }
          } catch (e) {
            logger.warn('Failed to parse SSE data:', e);
          }
        }
      }
    }
    
    // Clear timeout when stream completes normally
    if (streamTimeoutId) {
      clearTimeout(streamTimeoutId);
      streamTimeoutId = null;
    }
    
    logger.debug(`[Stream] Complete: ${eventCount} events received`);
    onComplete();
  } catch (error) {
    // Clear timeout on error
    if (streamTimeoutId) {
      clearTimeout(streamTimeoutId);
      streamTimeoutId = null;
    }
    
    // Distinguish between abort and actual errors
    if (error instanceof Error && error.name === 'AbortError') {
      const err = new Error('Stream timeout or cancelled - the LLM took too long to respond. Please try again.');
      logger.warn('[Stream] Request aborted:', err.message);
      // Call onError instead of silent return - user needs to know
      onError(err);
      return;
    }
    const err = error instanceof Error ? error : new Error(String(error));
    logger.error('[Stream] Error:', err);
    onError(err);
  }
}

// Git Operations API
export const getGitBranches = async (projectId: number): Promise<ApiResponse<{ currentBranch: string; branches: GitBranch[] }>> => {
  return apiCall<{ currentBranch: string; branches: GitBranch[] }>(
    `/projects/${projectId}/workspace/git/branches/`,
    { method: 'GET' }
  );
};

export const getGitCommits = async (
  projectId: number,
  options?: { limit?: number; branch?: string }
): Promise<ApiResponse<{ commits: GitCommit[]; count: number }>> => {
  const params = new URLSearchParams();
  if (options?.limit) params.append('limit', options.limit.toString());
  if (options?.branch) params.append('branch', options.branch);

  return apiCall<{ commits: GitCommit[]; count: number }>(
    `/projects/${projectId}/workspace/git/commits/?${params}`,
    { method: 'GET' }
  );
};

export const getGitRemoteStatus = async (projectId: number): Promise<ApiResponse<GitRemoteStatus>> => {
  return apiCall<GitRemoteStatus>(
    `/projects/${projectId}/workspace/git/remote-status/`,
    { method: 'GET' }
  );
};

export const gitPull = async (projectId: number): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/pull/`,
    { method: 'POST', body: JSON.stringify({}) }
  );
};

export const gitPush = async (
  projectId: number,
  options?: { branch?: string; force?: boolean }
): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/push/`,
    { method: 'POST', body: JSON.stringify(options || {}) }
  );
};

export const gitFetch = async (projectId: number): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/fetch/`,
    { method: 'POST', body: JSON.stringify({}) }
  );
};

export const gitCheckout = async (
  projectId: number,
  branch: string
): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/checkout/`,
    { method: 'POST', body: JSON.stringify({ branch }) }
  );
};

export const gitCommit = async (
  projectId: number,
  message: string,
  options?: { all?: boolean }
): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/commit/`,
    { method: 'POST', body: JSON.stringify({ message, ...options }) }
  );
};

export const gitRebase = async (
  projectId: number,
  branch: string
): Promise<ApiResponse<GitOperationResult>> => {
  return apiCall<GitOperationResult>(
    `/projects/${projectId}/workspace/git/rebase/`,
    { method: 'POST', body: JSON.stringify({ branch }) }
  );
};

// ============================================================================
// LLM Provider Management Types & API
// ============================================================================

export type LLMProviderScope = 'system' | 'team' | 'project' | 'user';
export type LLMProviderType = 'openai' | 'anthropic' | 'openrouter' | 'vllm' | 'ollama' | 'litemaas';

export interface LLMProviderPricing {
  prompt_price: number;  // USD per 1M tokens
  completion_price: number;  // USD per 1M tokens
}

export interface LLMProvider {
  id: number;
  scope: LLMProviderScope;
  name: string;
  provider_type: LLMProviderType;
  api_key: string;  // Masked (e.g., "********abcd")
  base_url?: string;
  available_models: Record<string, LLMProviderPricing>;
  pricing_data: Record<string, any>;
  team?: number;
  project?: number;
  user?: number;
  created_at: string;
  updated_at: string;
}

export interface LLMProviderCreate {
  scope: LLMProviderScope;
  instance_name: string;
  provider_type: LLMProviderType;
  api_key_plain: string;  // Plain text (will be encrypted server-side)
  base_url?: string;
  scope_team?: number;
  scope_project?: number;
  scope_user?: number;
}

export interface LLMProviderUpdate {
  instance_name?: string;
  api_key_plain?: string;
  base_url?: string;
  available_models?: any[];
  scope_user?: number;
  scope_team?: number;
  scope_project?: number;
}

export interface DiscoverModelsResponse {
  models: string[];
  available_models: Record<string, LLMProviderPricing>;
}

export interface TestConnectionResponse {
  success: boolean;
  message?: string;
}

export interface AvailableModelsResponse {
  [model_name: string]: {
    provider: LLMProvider;
    pricing: LLMProviderPricing;
  };
}

export interface UsageStats {
  total_messages: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost: string;  // Decimal as string
  by_provider: Array<{
    provider_id: number;
    provider_name: string;
    messages: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost: string;
  }>;
}

export interface DailyTrend {
  date: string;  // YYYY-MM-DD
  messages: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost: string;
}

export interface UserUsageStats extends UsageStats {
  user_id: number;
  username: string;
}

export interface ProviderUsageStats extends UsageStats {
  provider_id: number;
  provider_name: string;
}

// LLM Provider CRUD Operations
export const listLLMProviders = async (): Promise<ApiResponse<LLMProvider[]>> => {
  return apiCall<LLMProvider[]>('/llm-providers/', { method: 'GET' });
};

export const createLLMProvider = async (data: LLMProviderCreate): Promise<ApiResponse<LLMProvider>> => {
  return apiCall<LLMProvider>('/llm-providers/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getLLMProvider = async (id: number): Promise<ApiResponse<LLMProvider>> => {
  return apiCall<LLMProvider>(`/llm-providers/${id}/`, { method: 'GET' });
};

export const updateLLMProvider = async (
  id: number,
  data: LLMProviderUpdate
): Promise<ApiResponse<LLMProvider>> => {
  return apiCall<LLMProvider>(`/llm-providers/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export const deleteLLMProvider = async (id: number): Promise<ApiResponse<void>> => {
  return apiCall<void>(`/llm-providers/${id}/`, { method: 'DELETE' });
};

// LLM Provider Actions
export const discoverModels = async (id: number): Promise<ApiResponse<DiscoverModelsResponse>> => {
  return apiCall<DiscoverModelsResponse>(
    `/llm-providers/${id}/discover_models/`,
    { method: 'POST', body: JSON.stringify({}) }
  );
};

export const testConnection = async (id: number): Promise<ApiResponse<TestConnectionResponse>> => {
  return apiCall<TestConnectionResponse>(
    `/llm-providers/${id}/test_connection/`,
    { method: 'POST', body: JSON.stringify({}) }
  );
};

export const getAvailableModels = async (
  projectId?: number
): Promise<ApiResponse<AvailableModelsResponse>> => {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId.toString());
  
  const url = params.toString() 
    ? `/llm-providers/available_models/?${params}`
    : '/llm-providers/available_models/';
  
  return apiCall<AvailableModelsResponse>(url, { method: 'GET' });
};

// LLM Usage Statistics
export const getScopeUsageStats = async (
  scope: LLMProviderScope,
  scopeId?: number
): Promise<ApiResponse<UsageStats>> => {
  const params = new URLSearchParams({ scope });
  if (scopeId) params.append('scope_id', scopeId.toString());
  
  return apiCall<UsageStats>(
    `/llm-usage-stats/scope_stats/?${params}`,
    { method: 'GET' }
  );
};

export const getDailyUsageTrends = async (
  days: number = 30
): Promise<ApiResponse<DailyTrend[]>> => {
  return apiCall<DailyTrend[]>(
    `/llm-usage-stats/daily_trends/?days=${days}`,
    { method: 'GET' }
  );
};

export const getUserUsageStats = async (): Promise<ApiResponse<UserUsageStats>> => {
  return apiCall<UserUsageStats>(
    '/llm-usage-stats/user_stats/',
    { method: 'GET' }
  );
};

export const getProviderUsageStats = async (
  providerId?: number
): Promise<ApiResponse<ProviderUsageStats | ProviderUsageStats[]>> => {
  const url = providerId
    ? `/llm-usage-stats/provider_stats/?provider_id=${providerId}`
    : '/llm-usage-stats/provider_stats/';
  
  return apiCall<ProviderUsageStats | ProviderUsageStats[]>(url, { method: 'GET' });
};

// ============================================================================
// Phase 2: Monitoring & Analysis
// ============================================================================

export interface ContainerStats {
  container_id: string;
  container_name: string;
  status: string;
  memory_usage_mb: number;
  memory_limit_mb: number;
  memory_percent: number;
  cpu_percent: number;
  disk_usage_mb?: number;
  disk_limit_mb?: number;
  disk_percent?: number;
  network_in_bytes?: number;
  network_out_bytes?: number;
  timestamp: string;
  uptime_seconds?: number;
}

export interface ServiceStatsResponse {
  status: string;
  service: {
    id: number;
    name: string;
    container_name: string;
  };
  stats: ContainerStats;
}

export interface SyncCheckResponse {
  status: string;
  synced_count: number;
  orphaned_count: number;
  synced: Array<{
    id: number;
    name: string;
    container_name: string;
    status: string;
  }>;
  orphaned: Array<{
    id: number;
    name: string;
    container_name: string;
    status: string;
  }>;
  // Computed fields for UI
  is_synced?: boolean;
  issues?: Array<{
    type: 'orphaned_db_record' | 'missing_db_record' | 'status_mismatch';
    service_id?: number;
    service_name?: string;
    container_name?: string;
    details: string;
  }>;
}

/**
 * Get real-time container statistics for a service
 * CPU, memory, disk usage, network stats
 */
export const getServiceStats = async (serviceId: number): Promise<ApiResponse<ServiceStatsResponse>> => {
  return apiCall<ServiceStatsResponse>(`/project-services/${serviceId}/stats/`, {
    method: 'GET',
  });
};

export interface ProcessInfo {
  pid: string;
  user: string;
  cpu: string;
  mem: string;
  command: string;
}

export interface ServiceProcessesResponse {
  status: string;
  container_name: string;
  processes: ProcessInfo[];
}

/**
 * Get live process list for a running container (htop-style)
 */
export const getServiceProcesses = async (serviceId: number): Promise<ApiResponse<ServiceProcessesResponse>> => {
  return apiCall<ServiceProcessesResponse>(`/project-services/${serviceId}/top/`, {
    method: 'GET',
  });
};

/**
 * Check sync between database and actual Podman containers
 * Detects orphaned records, missing containers, status mismatches
 */
export const checkServiceSync = async (projectId: number): Promise<ApiResponse<SyncCheckResponse>> => {
  return apiCall<SyncCheckResponse>(`/project-services/sync_check/?project_id=${projectId}`, {
    method: 'GET',
  });
};

export interface AnalyzeStreamEvent {
  type: 'analyze_start' | 'analyze_progress' | 'analyze_complete' | 'analyze_error';
  path?: string;
  summary?: any;
  chunk?: any;
  progress?: number;
  message?: string;
  error?: string;
}

/**
 * Stream file analysis with SSE
 * Provides real-time progress events as file is analyzed
 */
export const streamFileAnalysis = async (
  projectId: number,
  path: string,
  mode: 'quick' | 'deep' = 'quick',
  onEvent: (event: AnalyzeStreamEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): Promise<void> => {
  try {
    const token = localStorage.getItem('accessToken');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const body = JSON.stringify({
      path,
      mode,
    });
    
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/workspace/files/analyze-stream/`,
      {
        method: 'POST',
        headers,
        body,
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    if (!response.body) {
      throw new Error('Response body is null');
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onEvent(data);
          } catch (e) {
            logger.warn('Failed to parse analyze event:', e);
          }
        }
      }
    }
    
    onComplete();
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    logger.error('File analysis stream error:', err);
    onError(err);
  }
};

// ============================================================================
// Phase 3: Edge Case Recovery
// ============================================================================

export interface RecreateContainerResponse {
  status: string;
  message: string;
  service: {
    id: number;
    name: string;
    container_name: string;
    status: string;
  };
  workspace_config?: {
    image: string;
    size: string;
  };
}

/**
 * Recreate an orphaned container
 * Used when database record exists but actual container is missing
 */
export const recreateOrphanedContainer = async (
  serviceId: number
): Promise<ApiResponse<RecreateContainerResponse>> => {
  return apiCall<RecreateContainerResponse>(
    `/project-services/${serviceId}/recreate/`,
    {
      method: 'POST',
    }
  );
};

/**
 * Resolve database inconsistencies
 * Removes orphaned DB records or recovers missing ones
 */
export const resolveDatabaseInconsistency = async (
  projectId: number,
  inconsistencyIds?: number[]
): Promise<ApiResponse<{ status: string; resolved: number; message: string }>> => {
  return apiCall(
    `/projects/${projectId}/workspace/services/resolve-sync/`,
    {
      method: 'POST',
      body: JSON.stringify({ inconsistency_ids: inconsistencyIds }),
    }
  );
};

// ============================================
// Copilot Mode API
// ============================================

export type AgentMode = 'assisted' | 'copilot';

export interface CopilotTool {
  name: string;
  description: string;
  params?: Array<{ name: string; type: string; description: string }>;
  source: 'builtin' | 'custom';
}

export interface CopilotHealthResponse {
  status: string;
  workspace: string;
  tools_dir: string;
  custom_tools: number;
}

/**
 * Check if Copilot Mode agent is available for a project
 */
export const getCopilotHealth = async (
  projectId: number
): Promise<ApiResponse<CopilotHealthResponse>> => {
  return apiCall(`/projects/${projectId}/copilot/health/`, { method: 'GET' });
};

/**
 * Get tools available in Copilot Mode
 */
export const getCopilotTools = async (
  projectId: number
): Promise<ApiResponse<{ tools: CopilotTool[] }>> => {
  return apiCall(`/projects/${projectId}/copilot/tools/`, { method: 'GET' });
};

/**
 * Send a chat message in Copilot Mode (non-streaming)
 */
export const sendCopilotMessage = async (
  projectId: number,
  message: string,
  options?: {
    mode?: string;
    temperature?: number;
    max_tokens?: number;
    context_files?: Array<{ path: string; content: string }>;
  }
): Promise<ApiResponse<{ content: string }>> => {
  return apiCall(`/projects/${projectId}/copilot/chat/`, {
    method: 'POST',
    body: JSON.stringify({
      message,
      ...options,
    }),
  });
};

/**
 * Stream a chat message in Copilot Mode
 */
export const streamCopilotMessage = async (
  projectId: number,
  message: string,
  onEvent: (type: StreamingEventType, data: any) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
  options?: {
    mode?: string;
    temperature?: number;
    max_tokens?: number;
    context_files?: Array<{ path: string; content: string }>;
  }
): Promise<void> => {
  try {
    const token = localStorage.getItem('accessToken');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const body = JSON.stringify({
      message,
      mode: options?.mode ?? 'agent',
      temperature: options?.temperature ?? 0.7,
      max_tokens: options?.max_tokens ?? 2000,
      context_files: options?.context_files ?? [],
    });
    
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/copilot/chat/stream/`,
      {
        method: 'POST',
        headers,
        body,
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    if (!response.body) {
      throw new Error('Response body is null');
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type) {
              onEvent(data.type, data);
            }
          } catch (e) {
            logger.warn('Failed to parse Copilot SSE data:', e);
          }
        }
      }
    }
    
    onComplete();
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    logger.error('[Copilot Stream] Error:', err);
    onError(err);
  }
};