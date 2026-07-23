/** Map platform API studio resources ↔ UI studio types. */

import type { ApiKnowledgeCanvas, ApiProjectAgent } from '@/lib/api'
import type { AgentDefinition, KnowledgeCanvas } from '@/types/studio'

export function mapApiCanvas(c: ApiKnowledgeCanvas): KnowledgeCanvas {
  return {
    id: c.id,
    name: c.name,
    desc: c.description ?? undefined,
    contentMd: c.content_md ?? '',
    origin: (c.origin as KnowledgeCanvas['origin']) || 'created',
    status: (c.status as KnowledgeCanvas['status']) || 'ready',
    chunks: c.chunks ?? undefined,
    mime: c.mime ?? undefined,
    sizeLabel: c.size_label ?? undefined,
    updatedAt: c.updated_at,
  }
}

export function mapApiAgent(a: ApiProjectAgent): AgentDefinition {
  return {
    id: a.id,
    name: a.name,
    role: a.role,
    desc: a.description,
    description: a.description,
    systemPrompt: a.system_prompt,
    prompt: a.system_prompt,
    tools: a.tools || [],
    active: a.active,
    source: 'everflow',
    managed: true,
  }
}
