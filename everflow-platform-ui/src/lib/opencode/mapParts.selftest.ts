/**
 * Run: npx tsx src/lib/opencode/mapParts.selftest.ts
 */
import {
  applyOcPartToMessage,
  mapOcMessage,
  mapPartToBlocks,
  mapQuestionRequest,
  messageHasPendingQuestion,
} from './mapParts'
import {
  applyPartFull,
  mapOcEvent,
  resolveQuestionMessage,
  upsertMessage,
  upsertQuestionMessage,
} from './mapEvents'
import type { ChatMessage } from '@/types/panels'
import type { OcPart } from './types'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

// --- Tool parts (OpenCode ToolPart shape) ---
const bashPart: OcPart = {
  id: 'p1',
  type: 'tool',
  callID: 'c1',
  tool: 'bash',
  state: {
    status: 'completed',
    input: { command: 'ls -la' },
    output: 'file.txt\n',
    title: 'list files',
  },
}
const bashBlocks = mapPartToBlocks(bashPart)
assert(bashBlocks.length === 1, 'bash → 1 block')
assert(bashBlocks[0].type === 'terminal', 'bash → terminal card')
assert(bashBlocks[0].terminal?.command === 'ls -la', 'bash command')
assert(bashBlocks[0].terminal?.output?.includes('file.txt'), 'bash output')

const editPart: OcPart = {
  id: 'p2',
  type: 'tool',
  callID: 'c2',
  tool: 'edit',
  state: {
    status: 'completed',
    input: {
      filePath: 'src/App.tsx',
      oldString: 'foo',
      newString: 'bar',
    },
    output: 'ok',
    title: 'edit App.tsx',
  },
}
const editBlocks = mapPartToBlocks(editPart)
assert(editBlocks[0].type === 'tool', 'edit → tool card')
assert(editBlocks[0].tool?.title?.includes('edit') || editBlocks[0].tool?.title?.includes('App'), 'edit title')
assert(editBlocks[0].tool?.status === 'done', 'edit done')
assert(editBlocks[0].tool?.body?.includes('App.tsx') || editBlocks[0].tool?.body === 'ok', 'edit body')

const runningRead: OcPart = {
  id: 'p3',
  type: 'tool',
  callID: 'c3',
  tool: 'read',
  state: {
    status: 'running',
    input: { filePath: 'README.md' },
    title: 'Reading README',
  },
}
const readBlocks = mapPartToBlocks(runningRead)
assert(readBlocks[0].tool?.status === 'running', 'read running')

// Complete message with only tools should not show "No response content"
const toolOnly = mapOcMessage({
  info: {
    id: 'a1',
    role: 'assistant',
    time: { created: 1, completed: 2 },
    finish: 'stop',
  },
  parts: [bashPart, editPart],
})
assert(
  !toolOnly.blocks?.some((b) => b.text?.includes('No response content')),
  'tool-only message has no empty placeholder',
)
assert(toolOnly.blocks?.some((b) => b.type === 'terminal'), 'tool-only keeps terminal')
assert(toolOnly.blocks?.some((b) => b.type === 'tool'), 'tool-only keeps edit')

// --- Question SSE events ---
const qEv = mapOcEvent({
  type: 'question.asked',
  properties: {
    id: 'req-1',
    sessionID: 'sess-1',
    questions: [
      {
        header: 'Style',
        question: 'Which UI library?',
        options: [
          { label: 'PatternFly', description: 'Red Hat' },
          { label: 'MUI', description: 'Material' },
        ],
      },
    ],
    tool: { messageID: 'a1', callID: 'c-q' },
  },
})
assert(qEv.kind === 'question', 'question.asked → question patch')
if (qEv.kind === 'question') {
  assert(qEv.requestId === 'req-1', 'request id')
  assert(qEv.questions.length === 1, 'one question')
}

const block = mapQuestionRequest({
  id: 'req-1',
  questions: [
    {
      header: 'Style',
      question: 'Which UI library?',
      options: [{ label: 'PatternFly' }, { label: 'MUI' }],
    },
  ],
})
assert(block.type === 'question', 'mapQuestionRequest type')
assert(block.questionRequest?.id === 'req-1', 'request id on block')
assert(block.options?.includes('PatternFly'), 'option labels')

let msgs: ChatMessage[] = [
  {
    id: 'a1',
    role: 'assistant',
    generationStatus: 'incomplete',
    blocks: [{ type: 'markdown', text: 'I need a choice.' }],
  },
]
// Pretend a tool-part orphan already rendered (pre-fix behavior)
msgs[0] = {
  ...msgs[0],
  blocks: [
    ...(msgs[0].blocks || []),
    {
      type: 'question',
      text: 'Which UI library?',
      options: ['PatternFly', 'MUI'],
    },
  ],
}
msgs = upsertQuestionMessage(msgs, {
  requestId: 'req-1',
  questions: [
    {
      question: 'Which UI library?',
      options: [{ label: 'PatternFly' }, { label: 'MUI' }],
    },
  ],
  messageId: 'a1',
})
assert(messageHasPendingQuestion(msgs[0]), 'pending question on message')
const qBlocks = (msgs[0].blocks || []).filter((b) => b.type === 'question')
assert(qBlocks.length === 1, `exactly one question card (got ${qBlocks.length})`)
assert(qBlocks[0].questionRequest?.id === 'req-1', 'keeps request-id card')

// question tool part must not produce a second interactive card
const qToolRunning: OcPart = {
  id: 'pq',
  type: 'tool',
  callID: 'cq',
  tool: 'question',
  messageID: 'a1',
  state: {
    status: 'running',
    input: {
      questions: [
        {
          header: 'Pick',
          question: 'A or B?',
          options: [{ label: 'A' }, { label: 'B' }],
        },
      ],
    },
  },
}
assert(mapPartToBlocks(qToolRunning).length === 0, 'running question tool → no UI block')

msgs = resolveQuestionMessage(msgs, 'req-1', 'answered')
assert(!messageHasPendingQuestion(msgs[0]), 'question resolved')

// --- message.updated without parts must not wipe tools ---
const withTools: ChatMessage = {
  id: 'a2',
  role: 'assistant',
  generationStatus: 'incomplete',
  blocks: mapPartToBlocks(bashPart),
}
const infoOnly = mapOcMessage({
  info: {
    id: 'a2',
    role: 'assistant',
    time: { created: 1 },
  },
  parts: [],
})
const merged = upsertMessage([withTools], infoOnly)
assert(merged[0].blocks?.some((b) => b.type === 'terminal'), 'upsert preserves tools')

// --- part_full streaming ---
const partEv = mapOcEvent({
  type: 'message.part.updated',
  properties: {
    sessionID: 's',
    part: { ...bashPart, messageID: 'a3', sessionID: 's' },
    time: 1,
  },
})
assert(partEv.kind === 'part_full', `tool part.updated → part_full (got ${partEv.kind})`)
if (partEv.kind === 'part_full') {
  assert(partEv.messageId === 'a3', 'messageId from part.messageID')
  const streamed = applyPartFull([], partEv.messageId, partEv.part)
  assert(streamed[0]?.blocks?.[0]?.type === 'terminal', 'streamed tool card')
}

// Incremental tool status update by callId
let m: ChatMessage = {
  id: 'a4',
  role: 'assistant',
  generationStatus: 'incomplete',
  blocks: mapPartToBlocks({
    ...runningRead,
    state: { status: 'running', input: { filePath: 'README.md' } },
  }),
}
m = applyOcPartToMessage(m, {
  ...runningRead,
  state: {
    status: 'completed',
    input: { filePath: 'README.md' },
    output: '# Hello',
    title: 'README.md',
  },
})
assert(m.blocks?.[0]?.tool?.status === 'done', 'tool status upsert')
assert(m.blocks?.[0]?.tool?.body?.includes('Hello'), 'tool output upsert')

console.log('mapParts/mapEvents selftest: ok')
