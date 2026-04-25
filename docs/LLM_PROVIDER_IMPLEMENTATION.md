# Multi-Provider LLM API Key Management Implementation

**Status**: Backend Complete ✅ | Frontend Pending ⏳  
**Last Updated**: 2025-01-XX  
**Implementation Time**: ~2 hours

---

## Overview

A comprehensive hierarchical API key management system enabling users to configure multiple LLM providers (OpenRouter, OpenAI, Anthropic, vLLM, Ollama) with 4-level cost center hierarchy:

1. **System-Wide** (admin only)
2. **Team-Wide** (team admins)
3. **Project-Wide** (project admins)
4. **User-Level** (all users)

Each chat message tracks token usage and costs, enabling detailed billing reports by scope/provider/user.

---

## Architecture

### Provider Resolution Hierarchy

```
User sends chat message
    ↓
Check session.provider FK (explicit selection)
    ↓ (if null)
Check user-level providers (matching selected_model if set)
    ↓ (if none)
Check project-level providers (user must have access)
    ↓ (if none)
Check team-level providers (user must be member)
    ↓ (if none)
Check system-level providers
    ↓ (if none)
Fallback to legacy llm_config.json
```

### Cost Tracking Flow

```
LLM API Response
    ↓
Extract: usage.prompt_tokens, usage.completion_tokens
    ↓
Look up pricing from provider.available_models[model_name]
    ↓
Calculate: (prompt_tokens/1M) * prompt_price + (completion_tokens/1M) * completion_price
    ↓
Store in ChatMessage: prompt_tokens, completion_tokens, total_tokens, estimated_cost, used_by_provider
```

---

## Backend Implementation

### 1. Data Models (`/backend/api/models.py`)

#### LLMProvider Model
```python
class LLMProvider(models.Model):
    SCOPE_CHOICES = [
        ('system', 'System-Wide'),
        ('team', 'Team-Wide'),
        ('project', 'Project-Wide'),
        ('user', 'User-Level'),
    ]
    
    # Core fields
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, db_index=True)
    name = models.CharField(max_length=255)  # e.g., "OpenAI GPT-4"
    provider_type = models.CharField(max_length=50)  # openai, anthropic, openrouter, vllm, ollama
    api_key = models.TextField()  # Fernet encrypted
    base_url = models.URLField(blank=True)  # For vLLM/Ollama
    
    # Scope foreign keys
    team = models.ForeignKey('Team', null=True, blank=True, on_delete=models.CASCADE)
    project = models.ForeignKey('Project', null=True, blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.CASCADE)
    
    # Model metadata
    available_models = models.JSONField(default=dict)  # {model_name: {prompt_price, completion_price}}
    pricing_data = models.JSONField(default=dict)  # Raw pricing from provider
    
    # Encryption methods
    def set_api_key(self, plain_key):
        cipher = Fernet(settings.FIELD_ENCRYPTION_KEY)
        self.api_key = cipher.encrypt(plain_key.encode()).decode()
    
    def get_api_key(self):
        cipher = Fernet(settings.FIELD_ENCRYPTION_KEY)
        return cipher.decrypt(self.api_key.encode()).decode()
```

#### ChatMessage Extensions
```python
class ChatMessage(models.Model):
    # Existing fields...
    
    # Cost tracking (new)
    used_by_provider = models.ForeignKey('LLMProvider', null=True, blank=True, on_delete=models.SET_NULL)
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
```

#### ChatSession Updates
```python
class ChatSession(models.Model):
    # New fields
    provider = models.ForeignKey('LLMProvider', null=True, blank=True, on_delete=models.SET_NULL)
    selected_model = models.CharField(max_length=255, null=True, blank=True)
    
    # Deprecated (legacy fallback)
    llm_id = models.CharField(max_length=100, default='ollama')
```

### 2. Discovery Service (`/backend/api/llm_discovery.py`)

Automatic model discovery with pricing extraction:

```python
async def discover_openrouter_models(api_key: str) -> Tuple[List[Dict], Dict]:
    """Query OpenRouter API for available models with pricing."""
    url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            
    available_models = {}
    for model in data.get('data', []):
        model_id = model.get('id')
        pricing = model.get('pricing', {})
        available_models[model_id] = {
            'prompt_price': float(pricing.get('prompt', 0)),
            'completion_price': float(pricing.get('completion', 0)),
        }
    
    return list(available_models.keys()), available_models
```

Providers supported:
- **OpenRouter**: API-based discovery (`/api/v1/models`)
- **OpenAI**: Static pricing dictionary (gpt-4, gpt-3.5-turbo, etc.)
- **Anthropic**: Static pricing (claude-3-opus, claude-3-sonnet, etc.)
- **vLLM**: OpenAI-compatible `/v1/models` endpoint
- **Ollama**: Local `/api/tags` endpoint

### 3. Cost Calculator (`/backend/api/cost_calculator.py`)

```python
def calculate_message_cost(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: Dict[str, float]
) -> Decimal:
    """Calculate cost from token usage and per-1M-token pricing."""
    prompt_price = Decimal(str(pricing.get('prompt_price', 0)))
    completion_price = Decimal(str(pricing.get('completion_price', 0)))
    
    prompt_cost = (Decimal(prompt_tokens) / Decimal('1000000')) * prompt_price
    completion_cost = (Decimal(completion_tokens) / Decimal('1000000')) * completion_price
    
    return prompt_cost + completion_cost
```

Statistics functions:
- `get_scope_usage_stats(scope, scope_id)`: Total messages, tokens, cost by scope
- `get_daily_usage_trends(days=30)`: Time series data
- `get_user_usage_stats(user)`: Per-user spend tracking
- `get_provider_usage_stats(provider)`: Per-provider metrics

### 4. REST API (`/backend/api/views.py`)

#### LLMProviderViewSet

```python
class LLMProviderViewSet(viewsets.ModelViewSet):
    serializer_class = LLMProviderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Hierarchical filtering - users see their own + accessible scopes."""
        user = self.request.user
        
        # Start with user's own providers
        queryset = LLMProvider.objects.filter(
            Q(scope='user', user=user)
        )
        
        # Add project providers (if user has access)
        user_projects = Project.objects.filter(
            Q(owner=user) | Q(contributors=user)
        )
        queryset |= LLMProvider.objects.filter(scope='project', project__in=user_projects)
        
        # Add team providers (if user is member)
        user_teams = user.teams.all()
        queryset |= LLMProvider.objects.filter(scope='team', team__in=user_teams)
        
        # Add system providers (visible to all)
        queryset |= LLMProvider.objects.filter(scope='system')
        
        return queryset.distinct()
    
    @action(detail=True, methods=['post'])
    async def discover_models(self, request, pk=None):
        """Manually trigger model discovery and update available_models."""
        provider = await sync_to_async(self.get_object)()
        api_key = provider.get_api_key()
        
        models, pricing = await LLMDiscoveryService.discover_models(
            provider.provider_type,
            api_key,
            provider.base_url
        )
        
        provider.available_models = pricing
        await sync_to_async(provider.save)()
        
        return Response({'models': models})
```

Endpoints:
- `GET /api/llm-providers/` - List accessible providers
- `POST /api/llm-providers/` - Create provider (admin-only for system/team/project)
- `GET /api/llm-providers/{id}/` - Retrieve provider details
- `PATCH /api/llm-providers/{id}/` - Update provider
- `DELETE /api/llm-providers/{id}/` - Delete provider
- `POST /api/llm-providers/{id}/discover_models/` - Trigger model discovery
- `POST /api/llm-providers/{id}/test_connection/` - Validate API key
- `GET /api/llm-providers/available_models/?project_id={id}` - Get models for project context

#### Chat Integration

```python
class ChatSessionViewSet(viewsets.ModelViewSet):
    async def _aget_ai_response(self, session, user_message_text):
        """Resolve provider hierarchy and call LLM API."""
        provider = await self._resolve_provider_hierarchy(session)
        
        if not provider:
            # Fallback to legacy llm_config.json
            return await self._call_legacy_llm(session, user_message_text)
        
        # Call provider API with cost tracking
        response_text = await self._call_provider_api(
            provider=provider,
            session=session,
            user_message_text=user_message_text
        )
        
        return response_text
    
    async def _resolve_provider_hierarchy(self, session):
        """Waterfall lookup: user → project → team → system."""
        user = await sync_to_async(lambda: session.user)()
        
        # 1. Check session.provider (explicit)
        if session.provider_id:
            return await sync_to_async(lambda: session.provider)()
        
        # 2. User-level providers
        user_providers = LLMProvider.objects.filter(scope='user', user=user)
        if session.selected_model:
            user_providers = user_providers.filter(
                available_models__has_key=session.selected_model
            )
        provider = await sync_to_async(user_providers.first)()
        if provider:
            return provider
        
        # 3. Project-level providers
        if session.project_id:
            project_providers = LLMProvider.objects.filter(
                scope='project',
                project_id=session.project_id
            )
            if session.selected_model:
                project_providers = project_providers.filter(
                    available_models__has_key=session.selected_model
                )
            provider = await sync_to_async(project_providers.first)()
            if provider:
                return provider
        
        # 4. Team-level providers
        user_teams = await sync_to_async(lambda: list(user.teams.all().values_list('id', flat=True)))()
        if user_teams:
            team_providers = LLMProvider.objects.filter(scope='team', team_id__in=user_teams)
            if session.selected_model:
                team_providers = team_providers.filter(
                    available_models__has_key=session.selected_model
                )
            provider = await sync_to_async(team_providers.first)()
            if provider:
                return provider
        
        # 5. System-level providers
        system_providers = LLMProvider.objects.filter(scope='system')
        if session.selected_model:
            system_providers = system_providers.filter(
                available_models__has_key=session.selected_model
            )
        provider = await sync_to_async(system_providers.first)()
        return provider
    
    async def _call_provider_api(self, provider, session, user_message_text):
        """Make LLM API call and extract token usage."""
        api_key = provider.get_api_key()
        model = session.selected_model or list(provider.available_models.keys())[0]
        
        # Build provider-specific URL
        if provider.provider_type == 'anthropic':
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        else:  # OpenAI-compatible
            base_url = provider.base_url or {
                'openai': 'https://api.openai.com/v1',
                'openrouter': 'https://openrouter.ai/api/v1',
                'vllm': provider.base_url,
                'ollama': 'http://localhost:11434/v1'
            }.get(provider.provider_type, 'https://api.openai.com/v1')
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        
        # Build messages from chat history
        messages = []
        chat_messages = await sync_to_async(
            lambda: list(session.messages.order_by('timestamp').values('role', 'content'))
        )()
        for msg in chat_messages:
            messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": user_message_text})
        
        # Make API call
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(url, headers=headers, json={
                "model": model,
                "messages": messages
            }) as response:
                response_data = await response.json()
        
        # Extract response content
        if provider.provider_type == 'anthropic':
            response_text = response_data['content'][0]['text']
        else:
            response_text = response_data['choices'][0]['message']['content']
        
        # Extract token usage
        usage = response_data.get('usage', {})
        prompt_tokens = usage.get('prompt_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
        
        # Calculate cost
        pricing = provider.available_models.get(model, {})
        estimated_cost = CostCalculator.calculate_message_cost(
            prompt_tokens,
            completion_tokens,
            pricing
        )
        
        # Store usage data temporarily on session
        session._last_response_tokens = {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'estimated_cost': estimated_cost,
            'provider': provider
        }
        
        return response_text
    
    @action(detail=True, methods=['post'])
    async def send_message(self, request, pk=None):
        """Send message and save token usage to ChatMessage."""
        session = await sync_to_async(self.get_object)()
        user_message_text = request.data.get('message')
        
        # Create user message
        user_message = await sync_to_async(ChatMessage.objects.create)(
            session=session,
            role='user',
            content=user_message_text,
            timestamp=timezone.now()
        )
        
        # Get AI response with cost tracking
        ai_response_text = await self._aget_ai_response(session, user_message_text)
        
        # Create AI message
        ai_message = await sync_to_async(ChatMessage.objects.create)(
            session=session,
            role='assistant',
            content=ai_response_text,
            timestamp=timezone.now()
        )
        
        # Save token usage if available
        if hasattr(session, '_last_response_tokens'):
            usage = session._last_response_tokens
            ai_message.prompt_tokens = usage['prompt_tokens']
            ai_message.completion_tokens = usage['completion_tokens']
            ai_message.total_tokens = usage['total_tokens']
            ai_message.estimated_cost = usage['estimated_cost']
            ai_message.used_by_provider = usage['provider']
            await sync_to_async(ai_message.save)()
            delattr(session, '_last_response_tokens')
        
        return Response({'message': ai_response_text})
```

### 5. Management Commands

```bash
# Migrate environment variables to system providers
python manage.py seed_system_providers

# With model discovery
python manage.py seed_system_providers --discover
```

Creates system-level providers from:
- `OPENAI_API_KEY` → System OpenAI provider
- `ANTHROPIC_API_KEY` → System Anthropic provider
- `OPENROUTER_API_KEY` → System OpenRouter provider
- `LITEMAAS_API_KEY` → System LiteMaaS provider (legacy)
- Ollama (no key required, localhost:11434)

### 6. Security & Encryption

**Encryption Setup** (`/backend/backend/settings.py`):
```python
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY', Fernet.generate_key().decode())
```

**API Key Masking** (serializer):
```python
def to_representation(self, instance):
    data = super().to_representation(instance)
    if instance.api_key:
        data['api_key'] = f"{'*' * 8}{instance.api_key[-4:]}"  # Show last 4 chars only
    return data
```

**Permission Enforcement**:
- System scope: `user.is_staff` only
- Team scope: `user.role == 'admin'` AND `user in team.members`
- Project scope: `user.role == 'admin'` AND `user in project.owner/contributors`
- User scope: `user == provider.user`

---

## Frontend Implementation Plan

### Task 12: Create API Functions (`src/lib/api.ts`)

```typescript
export interface LLMProvider {
  id: number;
  scope: 'system' | 'team' | 'project' | 'user';
  name: string;
  provider_type: 'openai' | 'anthropic' | 'openrouter' | 'vllm' | 'ollama';
  api_key: string;  // Masked
  base_url?: string;
  available_models: Record<string, {
    prompt_price: number;
    completion_price: number;
  }>;
  team?: number;
  project?: number;
  user?: number;
  created_at: string;
  updated_at: string;
}

export interface UsageStats {
  total_messages: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost: string;
  by_provider: Array<{
    provider_name: string;
    messages: number;
    cost: string;
  }>;
}

export const llmProviderApi = {
  list: () => apiClient.get<LLMProvider[]>('/llm-providers/'),
  
  create: (data: Partial<LLMProvider>) => 
    apiClient.post<LLMProvider>('/llm-providers/', data),
  
  update: (id: number, data: Partial<LLMProvider>) => 
    apiClient.patch<LLMProvider>(`/llm-providers/${id}/`, data),
  
  delete: (id: number) => 
    apiClient.delete(`/llm-providers/${id}/`),
  
  discoverModels: (id: number) => 
    apiClient.post<{models: string[]}>(`/llm-providers/${id}/discover_models/`),
  
  testConnection: (id: number) => 
    apiClient.post<{success: boolean}>(`/llm-providers/${id}/test_connection/`),
  
  getAvailableModels: (projectId?: number) => 
    apiClient.get<Record<string, LLMProvider>>('/llm-providers/available_models/', {
      params: { project_id: projectId }
    }),
};

export const usageStatsApi = {
  scopeStats: (scope: string, scopeId?: number) => 
    apiClient.get<UsageStats>('/llm-usage-stats/scope_stats/', {
      params: { scope, scope_id: scopeId }
    }),
  
  dailyTrends: (days = 30) => 
    apiClient.get<Array<{date: string; cost: string}>>('/llm-usage-stats/daily_trends/', {
      params: { days }
    }),
  
  userStats: () => 
    apiClient.get<UsageStats>('/llm-usage-stats/user_stats/'),
};
```

### Task 13: AddProviderDialog Component

Features:
- Provider type selector (OpenAI, Anthropic, OpenRouter, vLLM, Ollama)
- Scope selector (filtered by user permissions)
- Team/Project dropdown (conditional on scope)
- Instance name input
- API key input (password field with visibility toggle)
- Base URL input (for vLLM/Ollama)
- Test Connection button (shows loading spinner + success/error toast)
- Discover Models button (populates available_models)
- Save button (validates + creates provider)

### Task 14: Settings Page Updates

**My LLM Providers Section** (all users):
```tsx
<Card>
  <CardHeader>
    <CardTitle>My LLM Providers</CardTitle>
    <Button onClick={() => setAddDialogOpen(true)}>
      <Plus className="w-4 h-4 mr-2" />
      Add Provider
    </Button>
  </CardHeader>
  <CardContent>
    <div className="grid gap-4">
      {userProviders.map(provider => (
        <ProviderCard key={provider.id} provider={provider} onEdit={handleEdit} onDelete={handleDelete} />
      ))}
    </div>
  </CardContent>
</Card>
```

**ProviderCard Component**:
- Provider icon (OpenAI logo, Anthropic logo, etc.)
- Name + scope badge
- Model count badge
- Last 30 days spend
- Edit/Delete actions

**Admin Section** (staff/admin only):
- System Providers table (global)
- Team Providers table (all teams)
- Project Providers table (all projects)
- User Providers table (all users)

### Task 15: LLMUsageReport Page

**Layout**:
1. **Filters Row**:
   - Scope selector (System/Team/Project/User)
   - Team/Project dropdown (conditional)
   - Date range picker (last 7/30/90 days, custom)
   - Provider filter (multi-select)

2. **Metrics Cards**:
   - Total Messages (with trend)
   - Total Tokens (prompt + completion)
   - Total Cost (USD)
   - Avg Cost per Message

3. **Provider Breakdown Table**:
   ```
   Provider | Messages | Prompt Tokens | Completion Tokens | Total Cost | Actions
   OpenAI   | 1,234    | 456,789       | 123,456           | $45.67     | [Details]
   ```

4. **Daily Trend Chart** (Recharts line chart):
   - X-axis: Date
   - Y-axis: Cost (USD)
   - Lines: One per provider

5. **Export Button**:
   - CSV download with all filtered data

### Task 16: ModelSettings Component Updates

**Before** (simple dropdown):
```tsx
<Select value={selectedModel} onValueChange={setSelectedModel}>
  {models.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
</Select>
```

**After** (grouped by scope with pricing):
```tsx
<Select value={selectedModel} onValueChange={setSelectedModel}>
  <SelectGroup>
    <SelectLabel>System Providers</SelectLabel>
    {systemModels.map(m => (
      <SelectItem key={m.id} value={m.name}>
        <div className="flex items-center justify-between w-full">
          <span>{m.name}</span>
          <Badge variant="outline">${m.pricing.prompt_price}/${m.pricing.completion_price} per 1M tokens</Badge>
        </div>
      </SelectItem>
    ))}
  </SelectGroup>
  
  <SelectGroup>
    <SelectLabel>Team: Engineering</SelectLabel>
    {teamModels.map(m => ...)}
  </SelectGroup>
  
  <SelectGroup>
    <SelectLabel>My Providers</SelectLabel>
    {userModels.map(m => ...)}
  </SelectGroup>
</Select>

<div className="mt-2 text-sm text-muted-foreground">
  Using provider: <Badge>{resolvedProvider.name}</Badge>
  Estimated cost per 1K tokens: ${estimatedCost.toFixed(4)}
</div>
```

---

## Testing Checklist

### Backend Tests

- [ ] **Encryption**: Verify set_api_key → get_api_key returns original plaintext
- [ ] **Provider Discovery**: Test each provider type discovery function
- [ ] **Cost Calculation**: Verify math with known pricing examples
- [ ] **Hierarchy Resolution**: Test waterfall lookup with mock providers at each level
- [ ] **Permissions**: Verify admin-only enforcement for system/team/project scopes
- [ ] **Token Extraction**: Test with real API responses from each provider
- [ ] **Chat Integration**: Send message → verify ChatMessage has token usage saved

### Frontend Tests (TBD)

- [ ] **Add Provider Dialog**: Create provider → verify in list
- [ ] **Test Connection**: Invalid key → shows error toast
- [ ] **Discover Models**: Verify models populate dropdown
- [ ] **Model Selection**: Grouped display with pricing tooltips
- [ ] **Usage Report**: Filters → chart updates, export CSV downloads
- [ ] **Permissions**: Non-admin cannot see system providers section

---

## Usage Examples

### Admin: Add System OpenAI Provider

```bash
# Backend seeding (one-time)
python manage.py seed_system_providers --discover
```

Or via UI:
1. Navigate to Settings → System LLM Providers (admin only)
2. Click "Add Provider"
3. Select: Scope=System, Provider=OpenAI, Name="GPT-4 Production"
4. Paste API key
5. Click "Test Connection" → ✅ Success
6. Click "Discover Models" → Fetches gpt-4, gpt-3.5-turbo with pricing
7. Save

### User: Add Personal Anthropic Provider

1. Navigate to Settings → My LLM Providers
2. Click "Add Provider"
3. Select: Scope=User, Provider=Anthropic, Name="My Claude API"
4. Paste API key
5. Discover models → Claude-3-opus, Claude-3-sonnet
6. Save
7. Go to chatbot → Model dropdown shows "My Providers" section with Claude models

### Admin: View Team Spend Report

1. Navigate to Reports → LLM Usage
2. Select: Scope=Team, Team=Engineering, Date Range=Last 30 Days
3. See metrics: 5,432 messages, $234.56 total cost
4. Provider breakdown:
   - OpenAI: $198.43 (84%)
   - Anthropic: $36.13 (16%)
5. Click "Export CSV" → Download full report

---

## Migration Guide

### Existing Projects

1. **Backup database**: `cp backend/db.sqlite3 backend/db.sqlite3.backup`
2. **Install dependencies**: `pip install cryptography==42.0.0`
3. **Generate encryption key**:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
4. **Update `.env`**: Add `FIELD_ENCRYPTION_KEY=<generated_key>`
5. **Run migrations**: `python manage.py migrate`
6. **Seed system providers**: `python manage.py seed_system_providers --discover`
7. **Verify**: Check Django admin → LLM Providers → 1 system provider exists

### Breaking Changes

- `ChatSession.llm_id` deprecated (replaced by `provider` FK + `selected_model`)
- Chat messages now require token usage tracking (nullable for backward compat)
- Legacy `llm_config.json` still works but won't track costs

---

## Troubleshooting

### "Field encryption key not set"
**Solution**: Add `FIELD_ENCRYPTION_KEY` to `.env` file

### "No provider found" when sending chat message
**Solution**: Run `python manage.py seed_system_providers` or add user-level provider

### Model discovery returns empty list
**Solution**:
- Verify API key is valid via "Test Connection"
- Check provider type matches API (e.g., Anthropic key with OpenAI provider won't work)
- For vLLM/Ollama, verify base_url is reachable

### Token counts showing as null
**Solution**: Provider API must return `usage` object in response. Check provider API documentation.

### Cost calculations seem wrong
**Solution**: Verify `available_models` pricing is per 1M tokens (not per token or per 1K)

---

## Future Enhancements

- [ ] Rate limiting per provider/scope
- [ ] Budget alerts (email when scope exceeds threshold)
- [ ] Automatic model pricing refresh (daily cron job)
- [ ] Provider fallback (if primary fails, try secondary)
- [ ] Model aliasing (map internal names to provider IDs)
- [ ] Token usage predictions (estimate before sending)
- [ ] Cost optimization suggestions (cheaper models for simple tasks)

---

## API Reference

### Endpoints Summary

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/llm-providers/` | GET | List accessible providers | User |
| `/api/llm-providers/` | POST | Create provider | Admin |
| `/api/llm-providers/{id}/` | GET | Get provider details | User |
| `/api/llm-providers/{id}/` | PATCH | Update provider | Admin |
| `/api/llm-providers/{id}/` | DELETE | Delete provider | Admin |
| `/api/llm-providers/{id}/discover_models/` | POST | Refresh model list | Admin |
| `/api/llm-providers/{id}/test_connection/` | POST | Validate API key | Admin |
| `/api/llm-providers/available_models/` | GET | Get models for context | User |
| `/api/llm-usage-stats/scope_stats/` | GET | Get scope usage stats | User |
| `/api/llm-usage-stats/daily_trends/` | GET | Get daily cost trends | User |
| `/api/llm-usage-stats/user_stats/` | GET | Get user's usage stats | User |
| `/api/llm-usage-stats/provider_stats/` | GET | Get provider stats | Admin |

---

**Implementation Notes**:
- Total backend implementation time: ~2 hours
- Lines of code added: ~1,500
- Database migration tested: ✅ Success
- Management command tested: ✅ Success (created Ollama provider)
- Chat integration tested: ⏳ Pending (requires live LLM API)
- Frontend implementation: ⏳ Pending (6 tasks remaining)

