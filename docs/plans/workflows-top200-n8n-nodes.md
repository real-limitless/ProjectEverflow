---
title: Top 200 n8n Nodes → Everflow Open Implementation Plan
status: parked
execution: do-not-start-until-explicit-user-go
created: 2026-07-25
related:
  - docs/workflows-n8n.md
  - everflow-platform-api/app/services/workflows/registry.py
---

> **Status: PARKED.** This document is the full plan only.  
> **Do not implement** node executors, UI palette expansion, or registry changes until the user explicitly says to execute this plan.

# Plan: Top 200 n8n Nodes → Open-Source Everflow Implementation

## Goal

Identify the **top ~200 n8n nodes by real-world usage** (first 100 high-ROI + second 100 long-tail / still-common), then **clean-room reimplement** them in Everflow’s native workflow engine (import-compatible n8n JSON + executors + UI palette), so the Workflows tab can run popular n8n exports without running n8n itself.

**Catalog size:** 200 distinct node types (none repeated across List A and List B).

## Important constraints

| Constraint | Detail |
|---|---|
| **License** | n8n is *not* fully OSS (Sustainable Use / commercial terms). We **do not vendor or copy** n8n source. We keep Everflow’s existing **clean-room** engine that understands n8n-shaped documents. |
| **Compatibility target** | Match **node type strings**, common **parameters**, **credentials** names, and **connection types** (`main`, `ai_*`) so public template JSON imports and runs. |
| **Not 1:1 ops** | Many app nodes have dozens of operations. v1 = the **80% ops** used in templates (e.g. Slack `post message`, Sheets `append/read`). |
| **Current baseline** | Everflow already executes **~19 types** (Stock Agent Emailer acceptance set) in `registry.py` + `nodes/*`. |

## Ranking methodology

Combined three sources (2026):

1. **[n8n Pulse](https://n8n-pulse.gui.do/nodes/)** — estimated deployments from template insertions (best for core nodes).
2. **n8n Templates API** — occurrence + view-weighted counts over **2,000 public templates** (best for app/AI integrations).
3. **Full-workflow spot checks** — detail endpoints expose true core nodes (`set`, `if`, `wait`, `merge`, `webhook`, …) that search snippets omit.

Sticky Note dominates Pulse (#1) but is **canvas-only** (no runtime). Rank below treats it as P0 UI, not an executor.

---

## Current Everflow support (already done)

| n8n type | Status |
|---|---|
| `n8n-nodes-base.manualTrigger` | ✅ |
| `n8n-nodes-base.scheduleTrigger` | ✅ (hour-based scheduler) |
| `n8n-nodes-base.executeWorkflowTrigger` | ✅ (trigger only) |
| `n8n-nodes-base.set` | ✅ |
| `n8n-nodes-base.code` | ✅ (JS) |
| `n8n-nodes-base.if` | ✅ |
| `n8n-nodes-base.filter` | ✅ |
| `n8n-nodes-base.aggregate` | ✅ |
| `n8n-nodes-base.splitOut` | ✅ |
| `n8n-nodes-base.splitInBatches` | ✅ |
| `n8n-nodes-base.ftp` | ✅ |
| `n8n-nodes-base.extractFromFile` | ✅ |
| `n8n-nodes-base.convertToFile` | ✅ |
| `n8n-nodes-base.dataTable` | ✅ |
| `n8n-nodes-base.emailSend` | ✅ |
| `@n8n/n8n-nodes-langchain.lmChatOpenAi` | ✅ |
| `@n8n/n8n-nodes-langchain.agent` | ✅ (subset) |
| `@n8n/n8n-nodes-langchain.mcpClientTool` / `n8n-nodes-mcp.mcpClientTool` | ✅ stub-ish |

**UI palette today** only exposes a subset of the above (`WorkflowsPanel.tsx` `PALETTE`).

---

## Top 100 target catalog (ranked for Everflow investment)

Status: ✅ done · ⬜ missing · 🟡 partial  
Priority: **P0** foundation · **P1** unlocks most templates · **P2** popular apps · **P3** long-tail

### Tier A — Core engine (must-have; unblocks almost every export)

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 1 | Sticky Note | `n8n-nodes-base.stickyNote` | P0 | ⬜ UI-only |
| 2 | HTTP Request | `n8n-nodes-base.httpRequest` | P0 | ⬜ **#1 missing** |
| 3 | Edit Fields (Set) | `n8n-nodes-base.set` | P0 | ✅ |
| 4 | Code | `n8n-nodes-base.code` | P0 | ✅ |
| 5 | If | `n8n-nodes-base.if` | P0 | ✅ |
| 6 | Wait | `n8n-nodes-base.wait` | P0 | ⬜ |
| 7 | Merge | `n8n-nodes-base.merge` | P0 | ⬜ |
| 8 | Switch | `n8n-nodes-base.switch` | P0 | ⬜ |
| 9 | Split In Batches / Loop | `n8n-nodes-base.splitInBatches` | P0 | ✅ |
| 10 | Split Out | `n8n-nodes-base.splitOut` | P0 | ✅ |
| 11 | Filter | `n8n-nodes-base.filter` | P0 | ✅ |
| 12 | Aggregate | `n8n-nodes-base.aggregate` | P0 | ✅ |
| 13 | Limit | `n8n-nodes-base.limit` | P0 | ⬜ |
| 14 | Remove Duplicates | `n8n-nodes-base.removeDuplicates` | P0 | ⬜ |
| 15 | Sort | `n8n-nodes-base.sort` | P0 | ⬜ |
| 16 | Summarize | `n8n-nodes-base.summarize` | P1 | ⬜ |
| 17 | Compare Datasets | `n8n-nodes-base.compareDatasets` | P2 | ⬜ |
| 18 | Rename Keys | `n8n-nodes-base.renameKeys` | P1 | ⬜ |
| 19 | Date & Time | `n8n-nodes-base.dateTime` | P1 | ⬜ |
| 20 | Crypto | `n8n-nodes-base.crypto` | P1 | ⬜ |
| 21 | HTML | `n8n-nodes-base.html` | P1 | ⬜ |
| 22 | Markdown | `n8n-nodes-base.markdown` | P1 | ⬜ |
| 23 | XML | `n8n-nodes-base.xml` | P2 | ⬜ |
| 24 | Compression | `n8n-nodes-base.compression` | P2 | ⬜ |
| 25 | JWT | `n8n-nodes-base.jwt` | P2 | ⬜ |
| 26 | NoOp | `n8n-nodes-base.noOp` | P0 | ⬜ |
| 27 | Stop and Error | `n8n-nodes-base.stopAndError` | P0 | ⬜ |
| 28 | Execute Sub-workflow | `n8n-nodes-base.executeWorkflow` | P0 | ⬜ |
| 29 | Execute Sub-workflow Trigger | `n8n-nodes-base.executeWorkflowTrigger` | P0 | 🟡 trigger only |
| 30 | Execution Data | `n8n-nodes-base.executionData` | P2 | ⬜ |

### Tier B — Triggers

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 31 | Manual Trigger | `n8n-nodes-base.manualTrigger` | P0 | ✅ |
| 32 | Schedule Trigger | `n8n-nodes-base.scheduleTrigger` | P0 | 🟡 (expand cron) |
| 33 | Webhook | `n8n-nodes-base.webhook` | P0 | ⬜ |
| 34 | Respond to Webhook | `n8n-nodes-base.respondToWebhook` | P0 | ⬜ |
| 35 | Error Trigger | `n8n-nodes-base.errorTrigger` | P1 | ⬜ |
| 36 | Form Trigger | `n8n-nodes-base.formTrigger` | P1 | ⬜ |
| 37 | Chat Trigger | `@n8n/n8n-nodes-langchain.chatTrigger` | P1 | ⬜ |
| 38 | SSE Trigger | `n8n-nodes-base.sseTrigger` | P3 | ⬜ |
| 39 | Local File Trigger | `n8n-nodes-base.localFileTrigger` | P3 | ⬜ |
| 40 | Workflow Trigger (legacy) | `n8n-nodes-base.workflowTrigger` | P3 | ⬜ |

### Tier C — Files / network primitives

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 41 | Extract From File | `n8n-nodes-base.extractFromFile` | P0 | ✅ |
| 42 | Convert to File | `n8n-nodes-base.convertToFile` | P0 | ✅ |
| 43 | Read/Write Files from Disk | `n8n-nodes-base.readWriteFile` | P1 | ⬜ |
| 44 | FTP | `n8n-nodes-base.ftp` | P1 | ✅ |
| 45 | SSH | `n8n-nodes-base.ssh` | P1 | ⬜ |
| 46 | GraphQL | `n8n-nodes-base.graphql` | P2 | ⬜ |
| 47 | RSS Read | `n8n-nodes-base.rssFeedRead` | P2 | ⬜ |
| 48 | Edit Image | `n8n-nodes-base.editImage` | P2 | ⬜ |
| 49 | Data Table | `n8n-nodes-base.dataTable` | P1 | ✅ |
| 50 | Git | `n8n-nodes-base.git` | P1 | ⬜ (align with Everflow git) |

### Tier D — AI / LangChain (template-heavy)

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 51 | AI Agent | `@n8n/n8n-nodes-langchain.agent` | P0 | 🟡 expand tools/memory |
| 52 | OpenAI Chat Model | `@n8n/n8n-nodes-langchain.lmChatOpenAi` | P0 | ✅ |
| 53 | OpenAI (actions) | `@n8n/n8n-nodes-langchain.openAi` / base openAi | P1 | ⬜ |
| 54 | Gemini Chat Model | `@n8n/n8n-nodes-langchain.lmChatGoogleGemini` | P1 | ⬜ |
| 55 | Anthropic Chat Model | `@n8n/n8n-nodes-langchain.lmChatAnthropic` | P1 | ⬜ |
| 56 | OpenRouter Chat | `@n8n/n8n-nodes-langchain.lmChatOpenRouter` | P1 | ⬜ |
| 57 | Ollama Chat | `@n8n/n8n-nodes-langchain.lmChatOllama` | P1 | ⬜ |
| 58 | Groq / DeepSeek / xAI / Azure / Mistral chat | various `lmChat*` | P2 | ⬜ |
| 59 | Window Buffer Memory | `@n8n/n8n-nodes-langchain.memoryBufferWindow` | P0 | ⬜ |
| 60 | Structured Output Parser | `@n8n/n8n-nodes-langchain.outputParserStructured` | P0 | ⬜ |
| 61 | Basic LLM Chain | `@n8n/n8n-nodes-langchain.chainLlm` | P1 | ⬜ |
| 62 | Summarization Chain | `@n8n/n8n-nodes-langchain.chainSummarization` | P2 | ⬜ |
| 63 | Retrieval QA Chain | `@n8n/n8n-nodes-langchain.chainRetrievalQa` | P2 | ⬜ |
| 64 | Default Data Loader | `@n8n/n8n-nodes-langchain.documentDefaultDataLoader` | P1 | ⬜ |
| 65 | Recursive Text Splitter | `@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacterTextSplitter` | P1 | ⬜ |
| 66 | Embeddings OpenAI | `@n8n/n8n-nodes-langchain.embeddingsOpenAi` | P1 | ⬜ |
| 67 | Vector Store In-Memory | `@n8n/n8n-nodes-langchain.vectorStoreInMemory` | P1 | ⬜ |
| 68 | Vector Store Supabase / Pinecone / Qdrant / PGVector | various | P2 | ⬜ |
| 69 | Tool: Think / Calculator / Code / HTTP / Wikipedia / Workflow / SerpAPI | `@n8n/...tool*` | P1 | ⬜ |
| 70 | MCP Client Tool | `@n8n/n8n-nodes-langchain.mcpClientTool` | P0 | 🟡 |
| 71 | MCP Server Trigger | `@n8n/n8n-nodes-langchain.mcpTrigger` | P2 | ⬜ |
| 72 | Information Extractor / Text Classifier / Sentiment | langchain utils | P2 | ⬜ |
| 73 | AI Transform | `n8n-nodes-base.aiTransform` | P2 | ⬜ |

### Tier E — Communication & Google (highest app ROI)

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 74 | Telegram (+ Trigger) | `n8n-nodes-base.telegram` / `telegramTrigger` | P1 | ⬜ |
| 75 | Gmail (+ Trigger) | `n8n-nodes-base.gmail` / `gmailTrigger` | P1 | ⬜ |
| 76 | Slack (+ Trigger) | `n8n-nodes-base.slack` / `slackTrigger` | P1 | ⬜ |
| 77 | WhatsApp | `n8n-nodes-base.whatsApp` | P1 | ⬜ |
| 78 | Discord | `n8n-nodes-base.discord` | P1 | ⬜ |
| 79 | Microsoft Teams / Outlook | `microsoftTeams`, `microsoftOutlook` | P2 | ⬜ |
| 80 | Twilio | `n8n-nodes-base.twilio` | P2 | ⬜ |
| 81 | Send Email | `n8n-nodes-base.emailSend` | P0 | ✅ |
| 82 | Google Sheets | `n8n-nodes-base.googleSheets` | P0 | ⬜ |
| 83 | Google Drive (+ Trigger) | `googleDrive` / `googleDriveTrigger` | P1 | ⬜ |
| 84 | Google Docs | `n8n-nodes-base.googleDocs` | P2 | ⬜ |
| 85 | Google Calendar | `n8n-nodes-base.googleCalendar` | P2 | ⬜ |
| 86 | YouTube | `n8n-nodes-base.youTube` | P2 | ⬜ |

### Tier F — Data / CRM / Dev / Social (complete the 100)

| # | Node | n8n type | Pri | Status |
|---|---|---|---|---|
| 87 | Airtable | `n8n-nodes-base.airtable` | P1 | ⬜ |
| 88 | Notion | `n8n-nodes-base.notion` | P1 | ⬜ |
| 89 | Postgres | `n8n-nodes-base.postgres` | P1 | ⬜ |
| 90 | MySQL | `n8n-nodes-base.mySql` | P2 | ⬜ |
| 91 | Redis | `n8n-nodes-base.redis` | P2 | ⬜ |
| 92 | MongoDB | `n8n-nodes-base.mongoDb` | P2 | ⬜ |
| 93 | Supabase | `n8n-nodes-base.supabase` | P1 | ⬜ |
| 94 | S3 | `n8n-nodes-base.s3` | P1 | ⬜ |
| 95 | GitHub (+ Trigger) | `github` / `githubTrigger` | P1 | ⬜ |
| 96 | Jira | `n8n-nodes-base.jira` | P2 | ⬜ |
| 97 | HubSpot | `n8n-nodes-base.hubspot` | P2 | ⬜ |
| 98 | Facebook Graph API | `n8n-nodes-base.facebookGraphApi` | P2 | ⬜ |
| 99 | X (Twitter) / LinkedIn / Reddit | social nodes | P2 | ⬜ |
| 100 | WordPress | `n8n-nodes-base.wordpress` | P2 | ⬜ |

**Rough gap count (List A):** ~19 done → **~80+ still to implement** for the first 100 (some already partial).

Evidence highlights from sampling:

- Pulse top-10: Sticky, **HTTP Request**, Set, Code, OpenAI Chat, AI Agent, **Google Sheets**, If, Telegram, Wait.
- Templates (2k): Code, HTTP Request, Agent, Google Sheets, lmChatOpenAi, Gmail, Telegram, Google Drive dominate integrations.
- Full graphs always need: Set, If, Wait, Merge, Switch, Webhook — even when search cards hide them.

---

## List B — Next 100 (nodes 101–200, **not** in List A)

Sources: n8n Pulse category tails, Templates API ranks ~80–184+, official core/app nodes missing from List A, and agent-tool / trigger variants that show up in full workflow JSON.

All entries below are **⬜ missing** in Everflow today unless noted. Priority **P2** unless marked **P1** (still high value) or **P3** (nice-to-have).

### B1 — Core / binary / utility (missed in A)

| # | Node | n8n type | Pri |
|---|---|---|---|
| 101 | Item Lists (legacy) | `n8n-nodes-base.itemLists` | P2 |
| 102 | Move Binary Data | `n8n-nodes-base.moveBinaryData` | P1 |
| 103 | Read Binary File | `n8n-nodes-base.readBinaryFile` | P2 |
| 104 | Read Binary Files | `n8n-nodes-base.readBinaryFiles` | P2 |
| 105 | Write Binary File | `n8n-nodes-base.writeBinaryFile` | P2 |
| 106 | Spreadsheet File | `n8n-nodes-base.spreadsheetFile` | P2 |
| 107 | Read PDF | `n8n-nodes-base.readPDF` | P2 |
| 108 | Debug Helper | `n8n-nodes-base.debugHelper` | P2 |
| 109 | Execute Command | `n8n-nodes-base.executeCommand` | P1 |
| 110 | n8n (meta API) | `n8n-nodes-base.n8n` | P3 |
| 111 | Evaluation | `n8n-nodes-base.evaluation` | P3 |
| 112 | Evaluation Trigger | `n8n-nodes-base.evaluationTrigger` | P3 |
| 113 | Activation Trigger | `n8n-nodes-base.activationTrigger` | P3 |
| 114 | n8n Trigger | `n8n-nodes-base.n8nTrigger` | P3 |
| 115 | n8n Form (page) | `n8n-nodes-base.form` | P1 |
| 116 | TOTP | `n8n-nodes-base.totp` | P2 |
| 117 | LDAP | `n8n-nodes-base.ldap` | P2 |
| 118 | iCalendar | `n8n-nodes-base.iCalendar` | P3 |
| 119 | Quick Chart | `n8n-nodes-base.quickChart` | P2 |
| 120 | Hacker News | `n8n-nodes-base.hackerNews` | P3 |

### B2 — Messaging / email / notify (beyond List A)

| # | Node | n8n type | Pri |
|---|---|---|---|
| 121 | Mattermost | `n8n-nodes-base.mattermost` | P2 |
| 122 | Matrix | `n8n-nodes-base.matrix` | P3 |
| 123 | Rocket.Chat | `n8n-nodes-base.rocketchat` | P3 |
| 124 | Gotify | `n8n-nodes-base.gotify` | P3 |
| 125 | Pushover | `n8n-nodes-base.pushover` | P3 |
| 126 | Pushbullet | `n8n-nodes-base.pushbullet` | P3 |
| 127 | MessageBird | `n8n-nodes-base.messageBird` | P3 |
| 128 | SMS77 | `n8n-nodes-base.sms77` | P3 |
| 129 | SendGrid | `n8n-nodes-base.sendGrid` | P1 |
| 130 | Brevo (Sendinblue) | `n8n-nodes-base.sendInBlue` / `brevo` | P1 |
| 131 | Mailgun | `n8n-nodes-base.mailgun` | P2 |
| 132 | Mailchimp | `n8n-nodes-base.mailchimp` | P2 |
| 133 | Mailjet | `n8n-nodes-base.mailjet` | P3 |
| 134 | Postmark Trigger | `n8n-nodes-base.postmarkTrigger` | P3 |
| 135 | Email IMAP Trigger | `n8n-nodes-base.emailReadImap` | P1 |

### B3 — Google / Microsoft extras (beyond Sheets/Drive/Gmail/Calendar)

| # | Node | n8n type | Pri |
|---|---|---|---|
| 136 | Microsoft Excel | `n8n-nodes-base.microsoftExcel` | P1 |
| 137 | Microsoft OneDrive | `n8n-nodes-base.microsoftOneDrive` | P1 |
| 138 | Microsoft SharePoint | `n8n-nodes-base.microsoftSharePoint` | P2 |
| 139 | Microsoft SQL | `n8n-nodes-base.microsoftSql` | P2 |
| 140 | Microsoft Entra | `n8n-nodes-base.microsoftEntra` | P3 |
| 141 | Microsoft To Do | `n8n-nodes-base.microsoftToDo` | P3 |
| 142 | Google Analytics | `n8n-nodes-base.googleAnalytics` | P2 |
| 143 | Google Slides | `n8n-nodes-base.googleSlides` | P2 |
| 144 | Google Tasks | `n8n-nodes-base.googleTasks` | P2 |
| 145 | Google Contacts | `n8n-nodes-base.googleContacts` | P2 |
| 146 | Google Translate | `n8n-nodes-base.googleTranslate` | P3 |
| 147 | Google Ads | `n8n-nodes-base.googleAds` | P3 |
| 148 | Google BigQuery | `n8n-nodes-base.googleBigQuery` | P2 |
| 149 | Google Cloud Storage | `n8n-nodes-base.googleCloudStorage` | P2 |
| 150 | Google Business Profile | `n8n-nodes-base.googleBusinessProfile` | P3 |
| 151 | Google Chat | `n8n-nodes-base.googleChat` | P2 |
| 152 | G Suite Admin | `n8n-nodes-base.gSuiteAdmin` | P3 |

### B4 — Productivity / project trackers

| # | Node | n8n type | Pri |
|---|---|---|---|
| 153 | ClickUp | `n8n-nodes-base.clickUp` | P1 |
| 154 | Trello | `n8n-nodes-base.trello` | P1 |
| 155 | Asana | `n8n-nodes-base.asana` | P1 |
| 156 | Monday.com | `n8n-nodes-base.mondayCom` | P2 |
| 157 | Todoist | `n8n-nodes-base.todoist` | P2 |
| 158 | Linear | `n8n-nodes-base.linear` | P1 |
| 159 | GitLab | `n8n-nodes-base.gitlab` | P1 |
| 160 | GitLab Trigger | `n8n-nodes-base.gitlabTrigger` | P2 |
| 161 | GitHub Trigger | `n8n-nodes-base.githubTrigger` | P1 |
| 162 | Bitbucket Trigger | `n8n-nodes-base.bitbucketTrigger` | P3 |
| 163 | Jenkins | `n8n-nodes-base.jenkins` | P2 |
| 164 | CircleCI | `n8n-nodes-base.circleCi` | P3 |

### B5 — CRM / support / e‑commerce / finance

| # | Node | n8n type | Pri |
|---|---|---|---|
| 165 | Salesforce | `n8n-nodes-base.salesforce` | P1 |
| 166 | Pipedrive | `n8n-nodes-base.pipedrive` | P2 |
| 167 | Zendesk | `n8n-nodes-base.zendesk` | P1 |
| 168 | Zoho CRM | `n8n-nodes-base.zohoCrm` | P2 |
| 169 | HighLevel | `n8n-nodes-base.highLevel` | P2 |
| 170 | Odoo | `n8n-nodes-base.odoo` | P2 |
| 171 | HubSpot Trigger | `n8n-nodes-base.hubspotTrigger` | P2 |
| 172 | WooCommerce | `n8n-nodes-base.wooCommerce` | P1 |
| 173 | Shopify | `n8n-nodes-base.shopify` | P1 |
| 174 | Stripe | `n8n-nodes-base.stripe` | P1 |
| 175 | Stripe Trigger | `n8n-nodes-base.stripeTrigger` | P2 |
| 176 | QuickBooks | `n8n-nodes-base.quickbooks` | P2 |
| 177 | Xero | `n8n-nodes-base.xero` | P3 |
| 178 | PayPal | `n8n-nodes-base.payPal` | P3 |
| 179 | PagerDuty | `n8n-nodes-base.pagerDuty` | P2 |

### B6 — Data platforms / cloud / messaging infra

| # | Node | n8n type | Pri |
|---|---|---|---|
| 180 | Baserow | `n8n-nodes-base.baserow` | P1 |
| 181 | NocoDB | `n8n-nodes-base.nocoDb` | P1 |
| 182 | Dropbox | `n8n-nodes-base.dropbox` | P1 |
| 183 | Nextcloud | `n8n-nodes-base.nextCloud` | P2 |
| 184 | AWS S3 | `n8n-nodes-base.awsS3` | P1 |
| 185 | AWS Lambda | `n8n-nodes-base.awsLambda` | P2 |
| 186 | AWS SES | `n8n-nodes-base.awsSes` | P2 |
| 187 | AWS SQS / SNS | `awsSqs` / `awsSns` | P2 |
| 188 | Snowflake | `n8n-nodes-base.snowflake` | P2 |
| 189 | Elasticsearch | `n8n-nodes-base.elasticsearch` | P2 |
| 190 | MQTT | `n8n-nodes-base.mqtt` | P2 |
| 191 | Kafka | `n8n-nodes-base.kafka` | P2 |
| 192 | RabbitMQ | `n8n-nodes-base.rabbitmq` | P2 |
| 193 | AMQP | `n8n-nodes-base.amqp` | P3 |
| 194 | Redis Trigger | `n8n-nodes-base.redisTrigger` | P2 |
| 195 | Postgres Trigger | `n8n-nodes-base.postgresTrigger` | P2 |

### B7 — AI extras / agent tools / CMS / other apps

| # | Node | n8n type | Pri |
|---|---|---|---|
| 196 | LangChain Code | `@n8n/n8n-nodes-langchain.code` | P2 |
| 197 | Model Selector | `@n8n/n8n-nodes-langchain.modelSelector` | P2 |
| 198 | Guardrails | `@n8n/n8n-nodes-langchain.guardrails` | P1 |
| 199 | Memory Postgres / Redis / Mongo chat | `memoryPostgresChat`, `memoryRedisChat`, `memoryMongoDbChat` | P1 |
| 200 | Agent tool wrappers + extras pack | see sublist below (counts as #200 family) | P1 |

**#200 family — still not counted separately in List A** (implement as one “agent tools + triggers” workstream; each is its own type string):

| Sub | n8n type | Notes |
|---|---|---|
| 200a | `n8n-nodes-base.httpRequestTool` | Agent-callable HTTP |
| 200b | `n8n-nodes-base.gmailTool` | |
| 200c | `n8n-nodes-base.googleSheetsTool` | |
| 200d | `n8n-nodes-base.googleCalendarTool` | |
| 200e | `n8n-nodes-base.googleTasksTool` | |
| 200f | `n8n-nodes-base.wooCommerceTool` | |
| 200g | `n8n-nodes-base.rssFeedReadTool` | |
| 200h | `n8n-nodes-base.cryptoTool` | |
| 200i | `n8n-nodes-base.dateTimeTool` | |
| 200j | `@n8n/n8n-nodes-langchain.toolSearXng` | Aligns with Everflow SearXNG |
| 200k | `@n8n/n8n-nodes-langchain.toolWolframAlpha` | |
| 200l | `@n8n/n8n-nodes-langchain.outputParserItemList` | |
| 200m | `@n8n/n8n-nodes-langchain.outputParserAutofixing` | |
| 200n | `@n8n/n8n-nodes-langchain.embeddingsCohere` / Azure / HF / Mistral | |
| 200o | `@n8n/n8n-nodes-langchain.vectorStoreMilvus` / Weaviate / Redis / Mongo | |
| 200p | `@n8n/n8n-nodes-langchain.retrieverVectorStore` | |
| 200q | `@n8n/n8n-nodes-langchain.memoryManager` | |
| 200r | `n8n-nodes-base.perplexity` / `jinaAi` / `mistralAi` | |
| 200s | `n8n-nodes-base.webflow` / `ghost` / `strapi` / `contentful` | CMS |
| 200t | `n8n-nodes-base.homeAssistant` / `spotify` / `zoom` / `typeformTrigger` / `calendlyTrigger` | |

> **Note:** Sub-items 200a–200t are **additional type strings** beyond the numbered 101–199. Together with List A they exceed 200 concrete `type` IDs; treat **101–200** as the committed second wave and **200a–t** as the explicit backlog tail packed under workstream 200 so nothing popular is “forgotten.”

**Combined gap (A+B):** ≈ **180+ node types** still to implement from a 200+ catalog (Everflow has ~19).

---

## Architecture (how we implement in Everflow)

Keep the existing stack; extend it:

```
n8n JSON import
  → import_n8n.derive_graph / registry.SUPPORTED_NODE_TYPES
  → WorkflowEngine dispatch(nodes/__init__.py)
  → per-node executor (clean-room)
  → credentials_store + dry-run mocks
  → UI: PALETTE + NodeInspector props
```

### Package layout (proposed)

```
everflow-platform-api/app/services/workflows/
  registry.py                 # expand SUPPORTED_NODE_TYPES + credential types
  nodes/
    core.py                   # set/if/code/… (exists)
    flow.py                   # NEW: wait, merge, switch, limit, sort, noop, stopAndError
    http.py                   # NEW: httpRequest, respondToWebhook, graphql, rss
    files.py                  # expand readWriteFile
    integrations/             # NEW package, one module per app family
      google_sheets.py
      slack.py
      telegram.py
      …
    ai/                       # expand langchain-compatible executors
      memory.py
      parsers.py
      tools.py
      chains.py
  oauth/                      # NEW: OAuth2 connect flows for Google/Slack/etc.
docs/workflows-n8n.md         # catalog + ops coverage matrix
everflow-platform-ui/
  WorkflowsPanel.tsx palette  # full categorized palette
  nodeForms/*                 # per-type config panels (progressive)
```

### Shared infrastructure to build first (unblocks many nodes)

1. **HTTP client executor** — auth modes (none, header, bearer, basic, OAuth2, custom), binary, pagination hooks, retries → powers HTTP Request + most declarative app nodes.
2. **Webhook ingress** — project-scoped URL on platform API → starts run with payload; **Respond to Webhook** completes response.
3. **OAuth credential vault** — refresh tokens; map n8n credential type names (`googleSheetsOAuth2Api`, `slackOAuth2Api`, …).
4. **Merge / multi-input graph** — engine today is largely single-input fan-out; Merge needs multi-input join semantics.
5. **Wait / delay / resume** — timer + webhook-resume (`$execution.resumeUrl` parity subset).
6. **Sub-workflow call** — `executeWorkflow` → nested engine run with item passthrough.
7. **AI edge types** — already partially there (`ai_languageModel`, `ai_tool`); finish memory + outputParser wiring.
8. **Declarative node descriptor** (revive pattern from old `backend/api/workflow_engine/nodes/catalog/`) — props + HTTP routing for thin integrations without 300-line Python each.
9. **Fixture library** — 1 minimal n8n export + unit test per node; dry-run mocks for external APIs.
10. **UI** — categorized palette, unsupported badge, inspector schemas generated from descriptors.

### Open-source posture

- All new code stays in this repo under the project license.
- Document **compatibility matrix** (type × ops × typeVersion).
- Optional later: extract `everflow-workflow-nodes` as a standalone package if desired.
- Never copy n8n proprietary node source; use public docs + exported JSON parameter shapes + API docs of third parties.

---

## Phased delivery

### Phase 0 — Catalog & scaffolding (1–2 days)

- Commit `docs/workflows-top200.md` with List A + List B + ops checklist (machine-readable JSON optional).
- Auto-register nodes from a descriptor registry; expand UI palette from same source of truth.
- CI: fail if a “supported” type has no executor.

### Phase 1 — Foundation gaps (P0 core) — highest ROI

Order:

1. `httpRequest`
2. `webhook` + `respondToWebhook`
3. `wait` (delay mode first)
4. `merge` (append + combine by position)
5. `switch`
6. `noOp`, `stopAndError`, `limit`, `removeDuplicates`, `sort`
7. `executeWorkflow` (call child)
8. `stickyNote` (UI)
9. Expand `scheduleTrigger` full cron/interval
10. AI: `memoryBufferWindow`, `outputParserStructured`, harden `agent` tools

**Exit criteria:** import + dry-run of 10 popular “AI + HTTP + Sheets-less” templates; graph runs without “Unsupported node type”.

### Phase 2 — Google + comms (P1 apps)

- Google Sheets / Drive (OAuth)
- Gmail, Slack, Telegram (+ triggers where feasible)
- Airtable, Notion, Supabase, Postgres, S3, GitHub
- More LLM providers (Gemini, Anthropic, OpenRouter, Ollama)

**Exit criteria:** Stock-Agent-class + “Sheets → Slack notify” + “Webhook → Agent → Telegram” live with credentials.

### Phase 3 — Finish List A P2 + start List B P1

- Social, CRM, Microsoft, vector DBs, remaining List A transforms
- List B P1: Execute Command, IMAP email, SendGrid/Brevo, Excel/OneDrive, ClickUp/Trello/Asana/Linear, GitHub Trigger, Salesforce/Zendesk, WooCommerce/Shopify/Stripe, Baserow/NocoDB/Dropbox/AWS S3, Guardrails + chat memories, agent tool wrappers
- Ops coverage expansion (not just first action)
- Webhook auth, rate limits, binary pipelines (`moveBinaryData`, legacy binary nodes)

### Phase 4 — List B long-tail (P2–P3)

- Messaging infra (MQTT/Kafka/RabbitMQ), AWS extras, remaining Google/Microsoft
- CMS, marketing, finance, home automation
- Evaluation / n8n-meta nodes only if needed for import silence

### Phase 5 — Polish

- Node inspector forms for all supported types
- Expression parity (`$json`, `$node`, `$now`, `$env` subset already partially present)
- Marketplace workflow templates curated for Everflow-supported set
- Import report: “will run / partial / blocked” with missing ops listed

---

## Engineering touchpoints (existing code)

| Area | Path |
|---|---|
| Supported types | `everflow-platform-api/app/services/workflows/registry.py` |
| Dispatch | `.../nodes/__init__.py` |
| Engine | `.../engine.py` |
| Import | `.../import_n8n.py` + UI `n8nImport.ts` |
| UI palette | `everflow-platform-ui/src/components/panels/WorkflowsPanel.tsx` |
| Docs | `docs/workflows-n8n.md` |
| Tests | `tests/test_workflows_*.py` + fixtures |

Historical note: an older Django-era catalog (~20 integration nodes: Slack, GitHub, S3, …) lived under `backend/api/workflow_engine/nodes/catalog/` (commit `82840bd`) and was replaced by the n8n-compatible engine. **Re-use ideas**, not that code path (tree no longer present).

---

## Testing strategy

- **Unit:** each executor with fixed params + items.
- **Import parity:** real n8n export snippets per node.
- **Dry-run mocks:** no network in CI; optional live credential tests behind env flags.
- **Golden templates:** 5–10 public templates rewritten/stripped to supported ops; assert final items.
- **Regression:** existing Stock Agent Emailer suite must stay green.

---

## Success metrics

| Metric | Target |
|---|---|
| Supported n8n types in registry | ≥ **200** distinct types (List A + List B, excl. pure UI sticky) |
| List A (1–100) complete | 100% registered + tested (ops may be subset) |
| List B (101–200) complete | 100% registered; P1 ops covered; P3 may be thin stubs that pass import |
| Public template import “runnable” rate (top 200 templates) | ≥ 55% full / ≥ 80% partial with clear gaps |
| P0 core nodes | 100% of List A Tier A/B as ✅ |
| Docs | living matrix in `docs/workflows-top200.md` |

---

## Recommended first implementation slice (after approval)

Do **not** attempt all 100 at once. First PR series:

1. Scaffold descriptor registry + top-100 doc  
2. **HTTP Request** (full enough for generic API work)  
3. **Webhook + Respond to Webhook**  
4. **Wait / Merge / Switch / NoOp / StopAndError / Limit / Sort / RemoveDuplicates**  
5. AI memory + structured parser  
6. **Google Sheets** + OAuth  
7. Slack or Telegram  

That alone moves Everflow from “Stock Agent Emailer subset” to “general automation platform.”

---

## Open decisions (confirm on approval or next message)

1. **Scope of “100”:** official n8n nodes only (recommended) vs include community packages (Evolution API, Firecrawl, …)?  
2. **OAuth:** implement Google/Slack OAuth in platform-api now, or start with API-key/header-only nodes + HTTP Request?  
3. **Webhook hosting:** path under `/api/v1/projects/{id}/workflows/{wf}/webhook/{path}` (recommended) vs edge/sandbox?  
4. **AI providers:** wire through existing Everflow provider settings vs node-local credentials only?

Default recommendations: **official nodes only**, **API-key first + OAuth in Phase 2**, **platform-api webhooks**, **node-local credentials with optional org provider bridge**.
