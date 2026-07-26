"""Descriptor registration for every n8n node type Everflow can execute.

This module is the bridge between the executor functions in ``nodes/`` and
the descriptor registry. Importing it has the side effect of populating
``registry.REGISTRY`` and ``registry.SUPPORTED_NODE_TYPES``.

Per-tool sub-agents should add a single ``register(...)`` line in the
matching group section when they implement a new node. The CI invariant in
``tests/test_workflows_registry.py`` will fail if a ``SUPPORTED_NODE_TYPES``
entry lacks a descriptor, so it is also a check against half-implemented
node additions.
"""

from __future__ import annotations

from app.services.workflows.nodes import (
    airtable,
    agent_tools,
    ai_memory,
    ai_transform,
    binary,
    core,
    data_io,
    devops,
    discord,
    email_extra,
    facebook,
    files,
    flow,
    git,
    github,
    gmail,
    google_docs,
    google_drive,
    google_drive_trigger,
    google_calendar,
    google_extra,
    google_sheets,
    http,
    hubspot,
    image,
    jira,
    llm_agent,
    mcp_trigger,
    messaging_extra,
    microsoft,
    microsoft_extra,
    mongodb,
    mysql,
    notion,
    openai,
    postgres,
    redis,
    s3,
    slack,
    social,
    supabase,
    telegram,
    text_ai,
    trackers,
    twilio,
    utility_extra,
    whatsapp,
    wordpress,
    youtube,
    transforms,
    vector_store_in_memory,
    vector_store_pinecone,
    vector_store_pgvector,
    vector_store_qdrant,
    vector_store_supabase,
)
from app.services.workflows.registry import (
    NodeCategory,
    NodeDescriptor,
    register,
)


def _d(
    n8n_type: str,
    category: NodeCategory,
    fn,
    *,
    outputs: tuple[str, ...] = (),
    description: str = "",
    version: int = 1,
) -> NodeDescriptor:
    """Helper to build a descriptor from a function reference."""
    module = fn.__module__
    name = fn.__qualname__ or fn.__name__
    return register(
        NodeDescriptor(
            n8n_type=n8n_type,
            category=category,
            executor=f"{module}:{name}",
            outputs=outputs,
            description=description,
            version=version,
        )
    )


# ── Triggers ──────────────────────────────────────────────────────────
_d(
    "n8n-nodes-base.manualTrigger",
    "trigger",
    core.exec_trigger,
    description="Manual run trigger for a workflow.",
)
_d(
    "n8n-nodes-base.scheduleTrigger",
    "trigger",
    core.exec_trigger,
    description="Run on a schedule (cron/interval).",
)
_d(
    "n8n-nodes-base.executeWorkflowTrigger",
    "trigger",
    core.exec_trigger,
    description="Entry point when invoked by an executeWorkflow call.",
)
_d(
    "n8n-nodes-base.workflowTrigger",
    "trigger",
    core.exec_workflow_trigger,
    description="Workflow Trigger — legacy entry point when called from another workflow via webhook; emits one item with the caller's workflowId/executionId/data (mockable via ctx.mocks['workflow_call']).",
)
_d(
    "n8n-nodes-base.errorTrigger",
    "trigger",
    core.exec_error_trigger,
    description="Error Trigger — fires when the workflow run has a fatal error, emitting one item with the last error payload.",
)
_d(
    "n8n-nodes-base.formTrigger",
    "trigger",
    core.exec_form_trigger,
    description="Form Trigger — emit one item per form submission (mockable via ctx.mocks['form_submission']).",
)
_d(
    "@n8n/n8n-nodes-langchain.chatTrigger",
    "trigger",
    core.exec_chat_trigger,
    description="Chat Trigger — emit one item per chat message (mockable via ctx.mocks['chat_input']).",
)
_d(
    "@n8n/n8n-nodes-langchain.mcpTrigger",
    "trigger",
    mcp_trigger.exec_mcp_trigger,
    description="MCP Trigger — emit one item per received MCP message (mockable via ctx.mocks['mcp_payload'] / 'trigger_payload'; offline fallback synthesizes a JSON-RPC 2.0 message).",
)
_d(
    "n8n-nodes-base.telegramTrigger",
    "trigger",
    telegram.exec_telegram_trigger,
    description="Telegram Trigger — emit one item per received Telegram update via a configured webhook (mockable via ctx.mocks['telegram_update'] / 'trigger_payload'; offline fallback synthesizes a {update_id, message:{...}} payload).",
)
_d(
    "n8n-nodes-base.whatsAppTrigger",
    "trigger",
    whatsapp.exec_whatsapp_trigger,
    description="WhatsApp Trigger — emit one item per received WhatsApp Business Cloud API webhook (mockable via ctx.mocks['whatsapp_webhook'] / 'trigger_payload'; offline fallback synthesizes a {object: 'whatsapp_business_account', entry: [{id, changes: [{value: {messaging_product, metadata, messages}}]}]} payload).",
)
_d(
    "n8n-nodes-base.discordTrigger",
    "trigger",
    discord.exec_discord_trigger,
    description="Discord Trigger — emit one item per received Discord Gateway event (mockable via ctx.mocks['discord_event'] / 'trigger_payload'; offline fallback synthesizes a {t:'MESSAGE_CREATE', d:{id, channel_id, guild_id, author, content, timestamp}, s, op} payload). Honors parameters.event (default 'MESSAGE_CREATE').",
)
_d(
    "n8n-nodes-base.googleDriveTrigger",
    "trigger",
    google_drive_trigger.exec_google_drive_trigger,
    description="Google Drive Trigger — emit one item per Drive change (mockable via ctx.mocks['drive_changes'] / 'drive_response' / 'trigger_payload'; offline fallback synthesizes a {changes: [{fileId, file: {id, name, mimeType, modifiedTime, parents}, changeType, time}, ...], newStartPageToken, kind: 'drive#changeList'} payload with 3 mock_file_<i>.txt entries). Honors parameters.triggerOn ('specificFolder' / 'watchAll' / 'fileCreated' / 'fileUpdated'; default 'watchAll'), parameters.folderId (default 'root' for specificFolder), parameters.fileTypes (list of mime types; echoed), parameters.pollTimes (cron / everyMinute; echoed), parameters.event ('fileCreated' / 'fileUpdated' / 'fileDeleted' / 'fileShared'; default 'fileCreated').",
)
_d(
    "n8n-nodes-base.githubTrigger",
    "trigger",
    github.exec_github_trigger,
    description="GitHub Trigger — emit one item per received GitHub webhook event (mockable via ctx.mocks['github_event'] / 'trigger_payload'; offline fallback synthesizes a push event payload with {ref, before, after, repository, pusher, head_commit, commits, compare}). Honors parameters.events (list of event types; default ['push']), parameters.owner (default $json.owner), parameters.repository (default $json.repository/$json.repo), parameters.branch (optional; default ''). Emits one item with {event, ref, repository, pusher, headCommit, commits, compare, source: 'githubTrigger'}.",
)
_d(
    "n8n-nodes-base.sseTrigger",
    "trigger",
    core.exec_sse_trigger,
    description="SSE Trigger — emit one item per Server-Sent Event (mockable via ctx.mocks['sse_event']).",
)
_d(
    "n8n-nodes-base.localFileTrigger",
    "trigger",
    core.exec_local_file_trigger,
    description="Local File Trigger — emit one item per detected file change (mockable via ctx.mocks['file_change']).",
)

# ── Transform / control ───────────────────────────────────────────────
_d(
    "n8n-nodes-base.set",
    "transform",
    core.exec_set,
    description="Edit Fields — set/overwrite JSON fields on items.",
)
_d(
    "n8n-nodes-base.filter",
    "logic",
    core.exec_filter,
    description="Filter items by condition expression.",
)
_d(
    "n8n-nodes-base.if",
    "logic",
    core.exec_if,
    outputs=("true", "false"),
    description="Branch items into true/false outputs by condition.",
)
_d(
    "n8n-nodes-base.code",
    "transform",
    core.exec_code,
    description="Run JavaScript over items (clean-room VM).",
)
_d(
    "n8n-nodes-base.aggregate",
    "transform",
    core.exec_aggregate,
    description="Aggregate items into a single item (collect into array).",
)
_d(
    "n8n-nodes-base.summarize",
    "transform",
    transforms.exec_summarize,
    description="Summarize — collapse items into one item (count/sum/avg/min/max/first/last).",
)
_d(
    "n8n-nodes-base.renameKeys",
    "transform",
    transforms.exec_rename_keys,
    description="Rename Keys — rename JSON keys on each item (direct + regex, with overwrite flag).",
)
_d(
    "n8n-nodes-base.dateTime",
    "transform",
    transforms.exec_date_time,
    description="DateTime — format / parse / add / subtract / toIso / fromUnix / toUnix on a per-item value.",
)
_d(
    "n8n-nodes-base.crypto",
    "transform",
    transforms.exec_crypto,
    description="Crypto — hash (md5/sha1/sha256/sha512), hmac, AES-256-CBC encrypt/decrypt (PBKDF2), and generateUuid.",
)
_d(
    "n8n-nodes-base.html",
    "transform",
    transforms.exec_html,
    description="HTML — extractHtmlContent / htmlToText / extractHtmlLinkUrls / convertMarkdownToHtml / extractHtmlAttribute.",
)
_d(
    "n8n-nodes-base.markdown",
    "transform",
    transforms.exec_markdown,
    description="Markdown — convertHtmlToMarkdown / convertMarkdownToHtml / convertToText.",
)
_d(
    "n8n-nodes-base.xml",
    "transform",
    transforms.exec_xml,
    description="XML — xmlToJson / jsonToXml / modifyXml (XPath-lite set/append attribute).",
)
_d(
    "n8n-nodes-base.compression",
    "transform",
    transforms.exec_compression,
    description="Compression — gzip / deflate / zip compress or decompress on a binary property.",
)
_d(
    "n8n-nodes-base.jwt",
    "transform",
    transforms.exec_jwt,
    description="JWT — sign (HS256/HS384/HS512) and verify a JSON Web Token per item.",
)
_d(
    "n8n-nodes-base.executionData",
    "transform",
    transforms.exec_execution_data,
    description="Execution Data — emit one item with run-level metadata (runId, workflowId, triggerType, now, stepCount, nodeName).",
)
_d(
    "n8n-nodes-base.splitOut",
    "transform",
    core.exec_split_out,
    description="Split one item into many by a list field.",
)
_d(
    "n8n-nodes-base.splitInBatches",
    "logic",
    core.exec_split_in_batches,
    outputs=("done", "loop"),
    description="Loop items in batches with done/loop outputs.",
)

# ── Files / network I/O ───────────────────────────────────────────────
_d(
    "n8n-nodes-base.httpRequest",
    "input",
    http.exec_http_request,
    description="HTTP Request — single GET/POST/PUT/PATCH/DELETE with auth + headers + body.",
)
_d(
    "n8n-nodes-base.graphql",
    "input",
    http.exec_graphql,
    description="GraphQL — POST a query to an endpoint and return the JSON data field; honors the same auth modes as httpRequest.",
)
_d(
    "n8n-nodes-base.rssFeedRead",
    "input",
    http.exec_rss_feed_read,
    description="RSS Feed Read — fetch an RSS/Atom feed (parameters.url) and emit one item per entry with title/link/pubDate|published/contentSnippet/creator|author (mockable via ctx.mocks['rss']).",
)
_d(
    "n8n-nodes-base.extractFromFile",
    "transform",
    files.exec_extract_from_file,
    description="Parse binary (CSV/text) into JSON items.",
)
_d(
    "n8n-nodes-base.convertToFile",
    "transform",
    files.exec_convert_to_file,
    description="Convert a JSON field into a binary file (text/csv).",
)
_d(
    "n8n-nodes-base.readWriteFile",
    "input",
    files.exec_read_write_file,
    description="Read/Write File — read filesystem paths into item binary, or write item data out to filesystem paths. Uses ctx.mocks['filesystem'] when set; otherwise requires a developer-only baseDir.",
)
_d(
    "n8n-nodes-base.editImage",
    "transform",
    image.exec_edit_image,
    description="Edit Image — resize / rotate / flip / blur / grayscale / format a binary image. Uses Pillow when installed; otherwise falls back to ctx.mocks['image_output'] keyed by (operation, params_dict).",
)
_d(
    "n8n-nodes-base.ftp",
    "input",
    data_io.exec_ftp,
    description="FTP/SFTP list + download (mockable for dry-runs).",
)
_d(
    "n8n-nodes-base.git",
    "input",
    git.exec_git,
    description="Git — clone (shallow) / pull / commit / push / log. Mockable via ctx.mocks['git'] keyed by (operation, params_dict); falls back to dulwich when installed.",
)
_d(
    "n8n-nodes-base.ssh",
    "input",
    data_io.exec_ssh,
    description="SSH — execute a remote command and capture stdout/stderr/exitCode (mockable via ctx.mocks['ssh']; uses asyncssh when installed).",
)
_d(
    "n8n-nodes-base.dataTable",
    "data",
    data_io.exec_data_table,
    description="In-memory data table: create/delete table, get/insert rows.",
)
_d(
    "n8n-nodes-base.emailSend",
    "output",
    data_io.exec_email_send,
    description="Send an email via SMTP (mockable to capture only).",
)
_d(
    "@n8n/n8n-nodes-langchain.gmail",
    "output",
    gmail.exec_gmail,
    description="Gmail — send (and optionally wait) on a Gmail account via the Gmail API. Honors parameters.operation ('send' / 'sendAndWait'), parameters.to/subject/message/cc/bcc/html with $json fallbacks. Emits one item per input with {messageId, threadId, to, subject, body, labelIds, ok, source, operation}. Mockable via ctx.mocks['gmail_response'] (dict or callable (to, subject, body, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a <fake-...@mail.gmail.com> id and a <thread-...> thread id. Items with an empty subject are skipped.",
)
_d(
    "n8n-nodes-base.googleDrive",
    "output",
    google_drive.exec_google_drive,
    description="Google Drive — file operations via the Drive API. Honors parameters.operation ('upload' / 'download' / 'list' / 'delete'; default 'list'), parameters.name/mimeType/folderId/content/fileId/pageSize/query/dataMode with $json fallbacks. Upload emits one item per input with {id, name, mimeType, size, webViewLink, source: 'googleDrive'}; download emits {id, name, mimeType, content, size, source: 'googleDrive'} (content base64); list emits one item per file (or one item with files[] when dataMode='object'); delete emits {fileId, success, deletedAt, source: 'googleDrive'}. Mockable via ctx.mocks['drive_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a mock_file_<hex> id and a 1024-byte file for upload, base64 'mock file content' for download, three text/plain files for list, and a {success, fileId, deletedAt} envelope for delete.",
)
_d(
    "n8n-nodes-base.googleSheets",
    "output",
    google_sheets.exec_google_sheets,
    description="Google Sheets — read/append/update rows in a sheet via the Sheets API. Honors parameters.operation ('read'/'append'/'update'; default 'read'), parameters.sheetId (default $json.sheetId/$json.spreadsheetId), parameters.range (default 'A1:Z1000'), parameters.dataMode ('auto'/'array'/'object'; default 'array'), parameters.majorDimension ('ROWS'/'COLUMNS'; default 'ROWS'), parameters.data (default $json.data/$json.values). read emits one item per row (or one item with empty values) carrying {range, majorDimension, values, rowCount, source: 'googleSheets'}; append emits {spreadsheetId, updatedRange, updatedRows, updatedColumns, source: 'googleSheets'}; update emits {spreadsheetId, updatedRange, updatedRows, updatedColumns, updatedCells, source: 'googleSheets'}. Mockable via ctx.mocks['sheets_response'] (dict or callable (operation, sheetId, range, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a 2x3 mock values list for read, a {updates: {spreadsheetId, updatedRange, updatedRows: 1, updatedColumns: 3, updatedCells: 3}} envelope for append, and a {spreadsheetId, updatedRange, updatedRows: 1, updatedColumns: 3, updatedCells: 3} envelope for update. Items with empty sheetId are skipped.",
)
_d(
    "n8n-nodes-base.googleDocs",
    "output",
    google_docs.exec_google_docs,
    description="Google Docs — create/read/update a Google Doc via the Docs API. Honors parameters.operation ('create'/'read'/'update'; default 'read'), parameters.title (default $json.title/$json.name; used by create), parameters.content (default $json.content/$json.text; used by create/update), parameters.documentId (default $json.documentId/$json.id; required for read/update), parameters.replaceAll (bool; default False; used by update). create emits {documentId, title, body, revisionId, source: 'googleDocs'}; read emits {documentId, title, body, revisionId, source: 'googleDocs'}; update emits {documentId, revisionId, updatedAt, source: 'googleDocs'}. Mockable via ctx.mocks['docs_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a mock_doc_<hex> id with a paragraph body for create, a 'Mock Document' / 'Mock document content here.' envelope for read, and a {documentId, revisionId: '2', updatedAt: <iso>} envelope for update. Items with empty documentId on read/update are skipped.",
)
_d(
    "n8n-nodes-base.googleCalendar",
    "output",
    google_calendar.exec_google_calendar,
    description="Google Calendar — create/list/get/delete events on a calendar via the Calendar API. Honors parameters.operation ('create'/'list'/'get'/'delete'; default 'list'), parameters.calendarId (default 'primary'), parameters.dataMode ('array'/'object'; default 'array'; for list), parameters.maxResults (default 10; capped at 3 offline), parameters.timeMin/timeMax (default now / now+7d for list), parameters.q (search query; echoed for list). create reads summary (default $json.summary/$json.title), start (default $json.start/$json.startTime), end (default $json.end/$json.endTime), description, location, attendees (list of emails); emits one item per input with {eventId, summary, start, end, htmlLink, calendarId, operation, ok, source: 'googleCalendar'}. list emits one item per event (or one item with items[] when dataMode='object'). get/delete read eventId (default $json.eventId/$json.id); get emits {eventId, summary, start, end, htmlLink, source: 'googleCalendar'}; delete emits {eventId, success, deletedAt, source: 'googleCalendar'}. Mockable via ctx.mocks['calendar_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a mock_event_<hex> id with UTC start/end envelopes. Items with empty calendarId are skipped.",
)
_d(
    "n8n-nodes-base.telegram",
    "output",
    telegram.exec_telegram,
    description="Telegram — send a message to a chat via the Telegram Bot API (sendMessage). Honors parameters.chatId/text/parseMode (Markdown/HTML/MarkdownV2) with $json.chatId/chat_id/text/message fallbacks. Emits one item per input with {messageId, chatId, text, parseMode, ok, source}. Mockable via ctx.mocks['telegram_response'] (dict or callable (chatId, text, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {message_id, chat, date, text} envelope. Items with empty text are skipped.",
)
_d(
    "n8n-nodes-base.slack",
    "output",
    slack.exec_slack,
    description="Slack — send a message to a channel via the Slack Web API (chat.postMessage). Honors parameters.channel/text/blocks/asUser/linkNames with $json.channel/channelId/channel_id and $json.text/message fallbacks. Emits one item per input with {ok, channel, text, ts, message, asUser, linkNames, source, blocks?}. Mockable via ctx.mocks['slack_response'] (dict or callable (channel, text, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {ok, channel, ts, message:{type, text, user, ts}} envelope. Items with empty text and no blocks are skipped.",
)
_d(
    "n8n-nodes-base.microsoftTeams",
    "output",
    microsoft.exec_microsoft_teams,
    description="Microsoft Teams — send a message to a channel via the Microsoft Graph API (POST /teams/{team-id}/channels/{channel-id}/messages). Honors parameters.teamId/channelId/message/contentType (text/html) with $json.teamId/team_id, $json.channelId/channel_id and $json.message/text/content fallbacks. Emits one item per input with {messageId, teamId, channelId, message, contentType, createdDateTime, ok, source: 'microsoftTeams'}. Mockable via ctx.mocks['teams_response'] (dict or callable (channelId, message, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {id, createdDateTime, from:{user:{...}}, body:{contentType, content}} envelope. Items with empty message are skipped.",
)
_d(
    "n8n-nodes-base.microsoftOutlook",
    "output",
    microsoft.exec_microsoft_outlook,
    description="Microsoft Outlook — send an email via the Microsoft Graph API (POST /me/sendMail). Honors parameters.to/subject/body/bodyContentType (Text/HTML)/cc/bcc with $json.to/subject and $json.body/message/text fallbacks. Emits one item per input with {messageId, internetMessageId, to, subject, body, bodyContentType, sentDateTime, ok, source: 'microsoftOutlook'}. Mockable via ctx.mocks['outlook_response'] (dict or callable (to, subject, body, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {id, conversationId, internetMessageId, from:{emailAddress:...}, toRecipients, sentDateTime} envelope. Items with empty subject or empty body are skipped.",
)
_d(
    "n8n-nodes-base.whatsApp",
    "output",
    whatsapp.exec_whatsapp,
    description="WhatsApp — send a message to a phone number via the WhatsApp Business Cloud API. Honors parameters.phoneNumber/text/messageType ('text'/'template'; default 'text') with $json.phoneNumber/from/to and $json.text/message/body fallbacks. Emits one item per input with {messageId, phoneNumber, text, messageType, ok, contacts, source}. Mockable via ctx.mocks['whatsapp_response'] (dict or callable (phoneNumber, text, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {messaging_product, contacts, messages:[{id: wamid.<hex>, from, timestamp}]} envelope. Non-digits in phoneNumber are stripped for the API call; items with empty text are skipped.",
)
_d(
    "n8n-nodes-base.discord",
    "output",
    discord.exec_discord,
    description="Discord — send a message to a Discord channel via the bot API or webhook. Honors parameters.channelId/content/username/tts/embeds with $json.channelId/channel_id and $json.content/text/message fallbacks. Emits one item per input with {messageId, channelId, content, username, embeds, tts, ok, source: 'discord'}. Mockable via ctx.mocks['discord_response'] (dict or callable (channelId, content, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {id, channel_id, content, author:{id, username, bot}, timestamp, tts, embeds} envelope. Items with empty content and no embeds are skipped.",
)
_d(
    "n8n-nodes-base.github",
    "output",
    github.exec_github,
    description="GitHub — create/read/update issues, PRs, and repos via the GitHub REST API. Honors parameters.operation ('createIssue'/'getIssue'/'updateIssue'/'createPR'/'getPR'/'mergePR'/'createRepo'/'getRepo'; default 'getIssue'), parameters.owner (default $json.owner/$json.repoOwner), parameters.repository (default $json.repository/$json.repo; falls back to name for createRepo). Issue ops: parameters.issueNumber (default $json.issueNumber/$json.number), parameters.title (default $json.title), parameters.body (default $json.body/$json.description), parameters.labels (list; optional), parameters.assignees (list; optional), parameters.state ('open'/'closed'; optional). PR ops: parameters.pullNumber (default $json.pullNumber/$json.number), parameters.title, parameters.head, parameters.base, parameters.mergeMethod ('merge'/'squash'/'rebase'; default 'merge'). Repo ops: parameters.name (default $json.name), parameters.description (optional), parameters.private (bool; default False). Emits one item per input with {operation, owner, repository, <operation-specific fields>, htmlUrl, source: 'github'}. Mockable via ctx.mocks['github_response'] (dict or callable (operation, owner, repo, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a random number for create ops, the resolved number for get/update ops, a uuid hex sha for mergePR, and iso timestamps. Items with empty owner or repository are skipped.",
)
_d(
    "n8n-nodes-base.facebookGraphApi",
    "output",
    facebook.exec_facebook_graph_api,
    description="Facebook Graph API — make Graph API calls (GET/POST/DELETE) to Facebook/Meta endpoints. Honors parameters.operation ('get'/'post'/'delete'; default 'get'), parameters.node (the Graph API node/path, e.g. 'me', 'me/feed', '{page-id}/posts'; default $json.node/$json.path), parameters.fields (list of field names; optional; for GET), parameters.parameters (dict of query/body params; default $json.parameters/{}), parameters.version (API version; default 'v18.0'). Emits one item per input with {operation, node, version, <response fields>, source: 'facebookGraphApi'}. Mockable via ctx.mocks['facebook_response'] (dict or callable (operation, node, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline GET synthesizes {id: 'mock_fb_id', name: 'Mock Facebook Object', data: [], paging: {cursors: {before, after}}, version, node}, POST synthesizes {id: 'mock_post_<hex>', success: True, node, version}, DELETE synthesizes {success: True, node, version}. Items with empty node are skipped.",
)
_d(
    "n8n-nodes-base.jira",
    "output",
    jira.exec_jira,
    description="Jira — create/get/update/search/delete issues in Jira via the Jira REST API. Honors parameters.operation ('create'/'get'/'update'/'search'/'delete'; default 'get'), parameters.issueKey (default $json.issueKey/$json.key/$json.id; required for get/update/delete). For create: parameters.projectKey (default $json.projectKey; required), parameters.summary (default $json.summary/$json.title), parameters.description (default $json.description), parameters.issueType (default 'Task'), parameters.assignee (optional), parameters.labels (list; optional), parameters.priority (optional). For update: parameters.summary/description/status/assignee/priority (all optional). For search: parameters.jql (JQL query string; default $json.jql / 'project = DEMO ORDER BY created DESC'), parameters.maxResults (default 10), parameters.fields (list; default ['summary','status','assignee']), parameters.dataMode ('array'/'object'; default 'array'). create/get/update emit one item per input with {issueId, issueKey, summary, description, status, issueType, projectKey, self, source: 'jira'}; search emits one item per issue {issueId, issueKey, summary, status, assignee, source: 'jira'} (or one item with {issues, total, source: 'jira'} when dataMode='object'); delete emits {issueKey, success, deletedAt, source: 'jira'}. Mockable via ctx.mocks['jira_response'] (dict or callable (operation, issue_or_jql, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a random issue id and key for create, the echoed issueKey for get/update, up to 3 DEMO-N issues for search, and a {success, issueKey, deletedAt} envelope for delete. Items with empty issueKey (get/update/delete) or empty projectKey (create) are skipped.",
)
_d(
    "n8n-nodes-base.hubspot",
    "output",
    hubspot.exec_hubspot,
    description="HubSpot — create/get/update/list/delete contacts, companies, deals, and tickets in HubSpot via the CRM API. Honors parameters.operation ('create'/'get'/'update'/'list'/'delete'; default 'get'), parameters.resourceType ('contact'/'company'/'deal'/'ticket'; default 'contact'), parameters.objectId (default $json.objectId/$json.id/$json.contactId; required for get/update/delete). For create/update: parameters.properties (dict of property name → value; default $json.properties). For list: parameters.limit (default 10), parameters.properties (list of property names to include; optional), parameters.filter (dict; optional), parameters.dataMode ('array'/'object'; default 'array'). create/get/update emit one item per input with {objectId, properties, resourceType, createdAt?, updatedAt, source: 'hubspot'}; list emits one item per result {objectId, properties, resourceType, source: 'hubspot'} (or one item with {results, paging, limit, resourceType, source: 'hubspot'} when dataMode='object'); delete emits {objectId, archived, archivedAt, source: 'hubspot'}. Mockable via ctx.mocks['hubspot_response'] (dict or callable (operation, resourceType, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a random id with {firstname:'Mock', lastname:'User', email:'mock@example.com'} properties for create, the echoed objectId with {firstname, lastname, email, company} for get, echoed properties (or {firstname:'Updated'}) for update, up to 3 results for list, and a {archived: True, archivedAt} envelope for delete. Items with empty objectId (get/update/delete) are skipped.",
)
_d(
    "n8n-nodes-base.twitter",
    "output",
    social.exec_twitter,
    description="Twitter (X) — post a tweet / retweet / reply via the X/Twitter API v2. Honors parameters.operation ('tweet'/'retweet'/'reply'; default 'tweet'), parameters.text (default $json.text/$json.message/$json.tweet; used by tweet and reply), parameters.tweetId (default $json.tweetId/$json.id; used by retweet and reply). Emits one item per input with {tweetId, text, operation, authorId, createdAt, source: 'twitter'}. Mockable via ctx.mocks['twitter_response'] (dict or callable (operation, text, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {data: {id, text, edit_history_tweet_ids, author_id, created_at}, operation, source} envelope. Items with empty text are skipped for tweet/reply.",
)
_d(
    "n8n-nodes-base.linkedIn",
    "output",
    social.exec_linkedin,
    description="LinkedIn — post an update via the LinkedIn Share API. Honors parameters.text (default $json.text/$json.message/$json.content), parameters.visibility ('PUBLIC'/'CONNECTIONS'/'LOGGED_IN_MEMBERS'; default 'PUBLIC'), parameters.author (URN, e.g. urn:li:person:xxx; default $json.author/$json.authorUrn; falls back to urn:li:person:mock_person). Emits one item per input with {shareId, text, visibility, author, createdAt, source: 'linkedIn'}. Mockable via ctx.mocks['linkedin_response'] (dict or callable (text, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {id: 'urn:li:share:<random>', activity, text, visibility, author, created_at, source} envelope. Items with empty text are skipped.",
)
_d(
    "n8n-nodes-base.reddit",
    "output",
    social.exec_reddit,
    description="Reddit — post to a subreddit via the Reddit API. Honors parameters.title (default $json.title/$json.name), parameters.text (default $json.text/$json.body/$json.content), parameters.subreddit (default $json.subreddit/$json.sub), parameters.kind ('self'/'link'; default 'self'), parameters.url (default $json.url; used by link). Emits one item per input with {postId, title, text, subreddit, kind, author, createdAt, permalink, source: 'reddit'}. Mockable via ctx.mocks['reddit_response'] (dict or callable (title, text, subreddit, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a {id: 't3_<hex>', name, title, selftext, subreddit, kind, author, created_utc, permalink, url, source} envelope. Items with empty title or subreddit are skipped.",
)
_d(
    "n8n-nodes-base.twilio",
    "output",
    twilio.exec_twilio,
    description="Twilio — send an SMS or place an outbound call via the Twilio REST API. Honors parameters.operation ('send' / 'call'; default 'send'), parameters.from/to/message/options with $json.from/fromNumber, $json.to/toNumber and $json.message/body/text fallbacks. Emits one item per input with {sid, status, to, from, body (SMS only), operation, ok, source: 'twilio'}. Mockable via ctx.mocks['twilio_response'] (dict or callable (operation, from, to, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline SMS synthesizes a {sid: 'SM<32 hex>', status: 'queued', to, from, body, date_created, direction: 'outbound-api'} envelope and offline call synthesizes a {sid: 'CA<32 hex>', status: 'queued', to, from, direction: 'outbound-api', date_created} envelope. Empty 'to' is skipped; empty message on SMS is also skipped.",
)
_d(
    "n8n-nodes-base.notion",
    "output",
    notion.exec_notion,
    description="Notion — search/createPage/getPage/updatePage/queryDatabase via the Notion API. Honors parameters.operation ('search'/'createPage'/'getPage'/'updatePage'/'queryDatabase'; default 'search'), parameters.query (default $json.query/$json.search; for search), parameters.filter (dict with property/value; optional; for search/queryDatabase), parameters.pageSize (default 10; capped at 3 offline), parameters.parentId (default $json.parentId/$json.databaseId; for createPage), parameters.properties (dict; default $json.properties; for createPage/updatePage), parameters.children (list; optional; for createPage), parameters.pageId (default $json.pageId/$json.id; required for getPage/updatePage), parameters.databaseId (default $json.databaseId; required for queryDatabase), parameters.sorts (list; optional; for queryDatabase), parameters.dataMode ('array'/'object'; default 'array'; for search). search emits one item per result {pageId, title, url, object, createdTime, source: 'notion'} (or one item with results[] when dataMode='object'); createPage emits {pageId, url, parentId, properties, createdTime, source: 'notion'}; getPage emits {pageId, title, url, properties, createdTime, source: 'notion'}; updatePage emits {pageId, url, properties, lastEditedTime, source: 'notion'}; queryDatabase emits one item per result {pageId, title, createdTime, source: 'notion'}. Mockable via ctx.mocks['notion_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes mock_page_<i> ids. Items with empty pageId (getPage/updatePage) or empty databaseId (queryDatabase) are skipped.",
)
_d(
    "n8n-nodes-base.youTube",
    "output",
    youtube.exec_youtube,
    description="YouTube — search/get/list/upload videos via the YouTube Data API. Honors parameters.operation ('search'/'get'/'list'/'upload'; default 'search'). search reads q (default $json.q/$json.query/$json.search), maxResults (default 5), order (default 'relevance'), type (default 'video'); emits one item per result {videoId, title, description, channelId, publishedAt, source: 'youTube'} (or one item with items[] when dataMode='object'). get reads videoId (default $json.videoId/$json.id); emits {videoId, title, description, channelId, publishedAt, viewCount, likeCount, commentCount, source: 'youTube'}. list reads channelId (default $json.channelId), maxResults (default 5); emits one item per result {videoId, title, publishedAt, source: 'youTube'}. upload reads title (default $json.title), description (default $json.description), privacyStatus (default 'private'); emits {videoId, title, description, privacyStatus, uploadStatus, source: 'youTube'}. Mockable via ctx.mocks['youtube_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes mock_vid_<i> ids for search/list, a {id, snippet, statistics:{viewCount:1000, likeCount:100, commentCount:10}} envelope for get, and a mock_upload_<hex> id with uploadStatus='uploaded' for upload. Items with empty videoId on get or empty channelId on list are skipped.",
)
_d(
    "n8n-nodes-base.wordpress",
    "output",
    wordpress.exec_wordpress,
    description="WordPress — create/get/update/list/delete posts via the WordPress REST API. Honors parameters.operation ('create'/'get'/'update'/'list'/'delete'; default 'get'), parameters.postId (default $json.postId/$json.id; required for get/update/delete). For create/update: parameters.title (default $json.title), parameters.content (default $json.content/$json.body), parameters.status ('publish'/'draft'/'pending'/'private'; default 'draft' for create, 'publish' for update), parameters.author (optional; default 1), parameters.categories (list; optional), parameters.tags (list; optional), parameters.excerpt (optional). For list: parameters.perPage (default 10; capped at 3 offline), parameters.page (default 1), parameters.search (optional; echoed), parameters.status (default 'publish'). create/get/update emit one item per input {postId, title, content, status, author, date, link, operation, source: 'wordpress'} (title and content are rendered strings, not {rendered: ...} objects). list emits one item per post {postId, title, content, status, date, link, source: 'wordpress'} (or one item with {posts: [...], totalPosts, source: 'wordpress'} when dataMode='object'). delete emits {postId, deleted, source: 'wordpress'}. Mockable via ctx.mocks['wordpress_response'] (dict or callable (operation, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes a random int postId for create, echoes postId for get/update, generates up to 3 Mock Post entries for list, and a {deleted: True, previous: {...}} envelope for delete. Items with empty postId on get/update/delete are skipped.",
)

_d(
    "n8n-nodes-base.airtable",
    "output",
    airtable.exec_airtable,
    description="Airtable — list/create/read/update/upsert records in an Airtable base via the Airtable API. Honors parameters.operation ('list'/'create'/'read'/'update'/'upsert'; default 'list'), parameters.base (default $json.base/$json.baseId), parameters.table (default $json.table/$json.tableId/$json.tableName). For list: parameters.view (default 'Grid view'), parameters.maxRecords (default 10; capped at 3 offline), parameters.filterByFormula (optional), parameters.sort (list of {field, direction}; optional), parameters.dataMode ('array'/'object'; default 'array'). For create: parameters.records (list of {fields: {...}}; default $json.records/$json.data) or parameters.useItemFields (bool; use item json as fields). For read/update/upsert: parameters.recordId (default $json.recordId/$json.id); for update/upsert also parameters.fields (default $json.fields). list emits one item per record {recordId, fields, createdTime, source: 'airtable'} (or one item with records[] when dataMode='object'); create emits {recordId, fields, createdTime, source: 'airtable'}; read emits {recordId, fields, createdTime, source: 'airtable'}; update emits {recordId, fields, createdTime, source: 'airtable'}; upsert emits {recordId, fields, createdTime, updatedRecords, createdRecords, source: 'airtable'}. Mockable via ctx.mocks['airtable_response'] (dict or callable (operation, base, table, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes rec<i> ids with {Name, Status, Value} fields for list, a rec<hex> id for create, a {Name: 'Mock Record', Status: 'Active'} envelope for read, echoed fields for update, and a {records: [...], updatedRecords: 1, createdRecords: 0} envelope for upsert. Items with empty base or table are skipped; empty recordId on read/update is also skipped.",
)

_d(
    "n8n-nodes-base.postgres",
    "output",
    postgres.exec_postgres,
    description="Postgres — execute SQL queries and insert/update/upsert rows in PostgreSQL. Honors parameters.operation ('execute'/'insert'/'update'/'upsert'; default 'execute'), parameters.database (default $json.database/$json.databaseId; echoed only). For execute: parameters.query (SQL string; default $json.query/$json.sql; required), parameters.queryParameters (list of values; optional), parameters.dataMode ('array'/'object'; default 'array'). For insert/update/upsert: parameters.table (default $json.table/$json.tableName; required), parameters.schema (default 'public'), parameters.columns (list of column names; default $json.columns), parameters.values (list of row value lists; default $json.values/$json.data); for update/upsert also parameters.where (SQL WHERE clause; default $json.where), parameters.idColumn (default 'id'). execute emits one item per row {row, rowCount, command, source: 'postgres'} (or one item with rows[] when dataMode='object'); insert emits {affectedRows, command, lastInsertId, source: 'postgres'}; update emits {affectedRows, command, source: 'postgres'}; upsert emits {affectedRows, command, lastInsertId, upserted, source: 'postgres'}. Mockable via ctx.mocks['postgres_response'] (dict or callable (operation, query_or_table, params, item, ctx)) with ctx.mocks['db_response'] then ctx.mocks['http_response'] as fallbacks; offline synthesizes a 2-row SELECT response for execute, an {affectedRows: len(values_or_1), command: 'INSERT', lastInsertId} envelope for insert, an {affectedRows: 1, command: 'UPDATE'} envelope for update, and an {affectedRows: 1, command: 'INSERT', lastInsertId, upserted: True} envelope for upsert. Items with empty query (execute) or empty table (insert/update/upsert) are skipped.",
)

_d(
    "n8n-nodes-base.mySql",
    "output",
    mysql.exec_mysql,
    description="MySQL — execute SQL queries and insert/update/upsert rows in MySQL. Honors parameters.operation ('execute'/'insert'/'update'/'upsert'; default 'execute'), parameters.database (default $json.database/$json.databaseId; echoed only). For execute: parameters.query (SQL string; default $json.query/$json.sql; required), parameters.queryParameters (list of values; optional), parameters.dataMode ('array'/'object'; default 'array'). For insert/update/upsert: parameters.table (default $json.table/$json.tableName; required), parameters.columns (list of column names; default $json.columns), parameters.values (list of row value lists; default $json.values/$json.data); for update/upsert also parameters.where (SQL WHERE clause; default $json.where), parameters.idColumn (default 'id'). execute emits one item per row {row, rowCount, fieldCount, source: 'mySql'} (or one item with rows[] when dataMode='object'); insert/update/upsert emit {affectedRows, insertId, fieldCount, info, source: 'mySql'}. Mockable via ctx.mocks['mysql_response'] (dict or callable (operation, query_or_table, params, item, ctx)) with ctx.mocks['db_response'] then ctx.mocks['http_response'] as fallbacks; offline synthesizes a 2-row SELECT response for execute, an {affectedRows: 1, insertId, fieldCount: 0, info: 'Records: 1  Duplicates: 0  Warnings: 0'} envelope for insert, an {affectedRows: 1, insertId: 0, fieldCount: 0, info: 'Rows matched: 1  Changed: 1  Warnings: 0'} envelope for update, and an {affectedRows: 2, insertId, fieldCount: 0, info: 'Records: 1  Duplicates: 0  Warnings: 0'} envelope for upsert. Items with empty query (execute) or empty table (insert/update/upsert) are skipped.",
)

_d(
    "n8n-nodes-base.redis",
    "output",
    redis.exec_redis,
    description="Redis — get/set/delete/incr/decr/keys/publish via Redis. Honors parameters.operation ('get'/'set'/'delete'/'incr'/'decr'/'keys'/'publish'; default 'get'), parameters.key (default $json.key/$json.redisKey; required for get/set/delete/incr/decr). For set: parameters.value (default $json.value/$json.data), parameters.expire (int seconds; optional; default 0). For incr/decr: parameters.by (int; default 1). For keys: parameters.pattern (default '*'). For publish: parameters.channel (default $json.channel/$json.key; required), parameters.message (default $json.message/$json.value). get emits {key, value, exists, ttl, source: 'redis'}; set emits {key, value, ok, expire, source: 'redis'}; delete emits {key, deleted, source: 'redis'}; incr emits {key, value, incrementedBy, source: 'redis'}; decr emits {key, value, decrementedBy, source: 'redis'}; keys emits {keys, count, source: 'redis'}; publish emits {channel, message, subscribers, source: 'redis'}. Mockable via ctx.mocks['redis_response'] (dict or callable (operation, key, params, item, ctx)) with ctx.mocks['db_response'] then ctx.mocks['http_response'] as fallbacks; offline synthesizes {value: 'mock_value_for_<key>', exists: True, ttl: -1} for get, {ok: True} for set, {deleted: 1} for delete, {value: 1} for incr, {value: -1} for decr, {keys: ['mock_key_1','mock_key_2','mock_key_3'], count: 3} for keys, {subscribers: 1} for publish. Items with empty key (get/set/delete/incr/decr) or empty channel (publish) are skipped.",
)

_d(
    "n8n-nodes-base.mongoDb",
    "output",
    mongodb.exec_mongodb,
    description="MongoDb — find/insert/update/delete/aggregate documents in MongoDB. Honors parameters.operation ('find'/'insert'/'update'/'delete'/'aggregate'; default 'find'), parameters.collection (default $json.collection/$json.collectionName; required), parameters.database (default $json.database/$json.databaseName; echoed only), parameters.dataMode ('array'/'object'; default 'array'; find/aggregate only). For find: parameters.query (default $json.query / {}), parameters.limit (default 10), parameters.projection (optional), parameters.sort (optional). For insert: parameters.documents (list; default $json.documents/$json.data / wrap $json as single doc). For update: parameters.query (default $json.query / {}), parameters.update (default $json.update), parameters.upsert (bool; default False), parameters.multi (bool; default False). For delete: parameters.query (default $json.query / {}), parameters.limit (int; default 0 = all). For aggregate: parameters.pipeline (list; default $json.pipeline). find emits one item per document {document, count, source: 'mongoDb'} (or one item with documents[] when dataMode='object'); insert emits {insertedCount, insertedIds, acknowledged, source: 'mongoDb'}; update emits {matchedCount, modifiedCount, upsertedId, acknowledged, source: 'mongoDb'}; delete emits {deletedCount, acknowledged, source: 'mongoDb'}; aggregate emits one item per result {result, source: 'mongoDb'} (or one item with results[] when dataMode='object'). Mockable via ctx.mocks['mongodb_response'] (dict or callable (operation, collection, params, item, ctx)) with ctx.mocks['db_response'] then ctx.mocks['http_response'] as fallbacks; offline synthesizes up to 3 documents for find, an {insertedCount, insertedIds, acknowledged: True} envelope for insert, an {matchedCount: 1, modifiedCount: 1, upsertedId: None, acknowledged: True} envelope for update, an {deletedCount: 1, acknowledged: True} envelope for delete, and an {result: [{_id: 'group1', count: 5, total: 150}], ok: 1} envelope for aggregate. Items with empty collection are skipped.",
)

_d(
    "n8n-nodes-base.supabase",
    "output",
    supabase.exec_supabase,
    description="Supabase — select/insert/update/upsert rows in a Supabase table via the PostgREST API. Honors parameters.operation ('select'/'insert'/'update'/'upsert'; default 'select'), parameters.table (default $json.table/$json.tableName; required), parameters.schema (default 'public'). For select: parameters.columns (default '*'), parameters.limit (default 10; capped at 3 offline), parameters.filter (dict of column → value; optional), parameters.order (dict with column/ascending; optional), parameters.dataMode ('array'/'object'; default 'array'). For insert: parameters.records (list of dicts; default $json.records/$json.data; or wrap $json as single record). For update/upsert: parameters.records (list of dicts; default $json.records/$json.data), parameters.match (dict of column → value for WHERE; default $json.match); for upsert also parameters.onConflict (column name; default 'id'). select emits one item per row {row, count, source: 'supabase'} (or one item with data[] when dataMode='object'); insert/update/upsert emit {data, count, status, source: 'supabase'}; upsert also has upserted: True. Mockable via ctx.mocks['supabase_response'] (dict or callable (operation, table, params, item, ctx)) with ctx.mocks['db_response'] then ctx.mocks['http_response'] as fallbacks; offline synthesizes up to 3 rows for select, a {data: [{id, **first_record_fields}], count: 1, status: 201} envelope for insert, a {data: [{id: match_id, **updated_fields}], count: 1, status: 200} envelope for update, and a {data: [{id: match_id_or_new, **fields}], count: 1, status: 201, upserted: True} envelope for upsert. Items with empty table are skipped.",
)

_d(
    "n8n-nodes-base.s3",
    "output",
    s3.exec_s3,
    description="S3 — upload/download/list/delete files in an S3 bucket via the AWS S3 API. Honors parameters.operation ('upload'/'download'/'list'/'delete'; default 'list'), parameters.bucket (default $json.bucket/$json.bucketName; required), parameters.key (default $json.key/$json.fileName; required for download/delete), parameters.content (base64 or bytes; default $json.content/$json.data; for upload), parameters.contentType (default 'application/octet-stream'), parameters.prefix (default ''; for list), parameters.maxKeys (default 100; for list), parameters.delimiter (optional; for list), parameters.dataMode ('array'/'object'; default 'array'; for list). upload emits {key, bucket, etag, location, size, source: 's3'}; download emits {key, bucket, body, contentType, contentLength, etag, source: 's3'} (body base64); list emits one item per file {key, lastModified, etag, size, source: 's3'} (or one item with contents[] when dataMode='object'); delete emits {key, bucket, deleted, source: 's3'}. Mockable via ctx.mocks['s3_response'] (dict or callable (operation, bucket, params, item, ctx)) with ctx.mocks['http_response'] as fallback; offline synthesizes an ETag/LOCATION envelope for upload, base64 'mock s3 file content' for download, three mock_file_<i>.txt entries for list, and a {Deleted: [{Key}]} envelope for delete. Items with empty bucket are skipped; empty key on download/delete is also skipped.",
)

# ── AI / LangChain / MCP ──────────────────────────────────────────────
_d(
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "ai",
    llm_agent.exec_lm_chat_openai,
    description="OpenAI chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
    "ai",
    llm_agent.exec_lm_chat_google_gemini,
    description="Google Gemini chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "ai",
    llm_agent.exec_lm_chat_anthropic,
    description="Anthropic Claude chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
    "ai",
    llm_agent.exec_lm_chat_openrouter,
    description="OpenRouter chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatOllama",
    "ai",
    llm_agent.exec_lm_chat_ollama,
    description="Ollama local chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatGroq",
    "ai",
    llm_agent.exec_lm_chat_groq,
    description="Groq chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
    "ai",
    llm_agent.exec_lm_chat_deepseek,
    description="DeepSeek chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatXAiGrok",
    "ai",
    llm_agent.exec_lm_chat_xai_grok,
    description="xAI Grok chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
    "ai",
    llm_agent.exec_lm_chat_azure_openai,
    description="Azure OpenAI chat language model (ai_languageModel sub-node); resolves endpoint + deployment.",
)
_d(
    "@n8n/n8n-nodes-langchain.lmChatMistralCloud",
    "ai",
    llm_agent.exec_lm_chat_mistral_cloud,
    description="Mistral Cloud chat language model (ai_languageModel sub-node).",
)
_d(
    "@n8n/n8n-nodes-langchain.agent",
    "ai",
    llm_agent.exec_agent,
    description="AI agent — runs LLM with connected tools/memory.",
)
_d(
    "@n8n/n8n-nodes-langchain.chainLlm",
    "ai",
    llm_agent.exec_chain_llm,
    description="Basic LLM Chain — prompt template + connected LM, emit {text, model, usage} per item (mockable via ctx.mocks['chain_output']).",
)
_d(
    "@n8n/n8n-nodes-langchain.aiTransform",
    "ai",
    ai_transform.exec_ai_transform,
    description="AI Transform — evaluate a prompt template (with {{ $json.field }} expressions) and emit one item per input carrying the transformation under parameters.outputField (default 'output'). Honors an optional parameters.instructions system prompt. Mockable via ctx.mocks['chain_output'] (callable: (prompt, item, params, ctx)) with ctx.mocks['agent_output'] as fallback; offline fallback echoes the resolved prompt.",
)
_d(
    "@n8n/n8n-nodes-langchain.chainSummarization",
    "ai",
    llm_agent.exec_chain_summarization,
    description="Summarization Chain — chunk + summarize input text via connected LM, emit {summary, model, sourceLength} per item (mockable via ctx.mocks['chain_output']; offline fallback picks first 2 sentences).",
)
_d(
    "@n8n/n8n-nodes-langchain.chainRetrievalQa",
    "ai",
    llm_agent.exec_chain_retrieval_qa,
    description="Retrieval QA Chain — retrieve docs via connected retriever, answer via connected LM; emit {text, question, sourceDocuments, model} per item (mockable via ctx.mocks['chain_output'] / 'retriever_output'; offline returns snippet or 'I don't have enough information to answer that.').",
)
_d(
    "@n8n/n8n-nodes-langchain.documentDefaultDataLoader",
    "ai",
    llm_agent.exec_document_default_data_loader,
    description="Default Document Loader — wrap input text/binary as LangChain Document(s) with {pageContent, metadata}; honors a connected text-splitter's chunkSize for greedy chunking (mockable via ctx.mocks['document_output'] / ctx.mocks['loader_output']).",
)
_d(
    "@n8n/n8n-nodes-langchain.embeddingsOpenAi",
    "ai",
    llm_agent.exec_embeddings_openai,
    description="OpenAI Embeddings — embed text via text-embedding-3-small/large or ada-002; emits {embedding, model, dimensions} per item (mockable via ctx.mocks['embeddings_output']; offline returns a deterministic SHA-256-based vector).",
)
_d(
    "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
    "ai",
    llm_agent.exec_text_splitter_recursive_character,
    description="Recursive Character Text Splitter — split text into chunks of chunkSize characters with chunkOverlap; honors parameters.separators (default ['\\n\\n','\\n',' ','']). Emits one item per chunk {text, chunkIndex, chunkSize, source, totalChunks} (mockable via ctx.mocks['splitter_output'] / ctx.mocks['document_output']).",
)
_d(
    "@n8n/n8n-nodes-langchain.vectorStoreInMemory",
    "ai",
    vector_store_in_memory.exec_vector_store_in_memory,
    description="In-memory Vector Store — insert/load/retrieve LangChain documents with cosine similarity (offline, mock-driven). Honors parameters.mode ('insert'/'load'/'retrieve'), parameters.topK (default 4); resolves a connected embedding model via ai_embedding for the vector (mockable via ctx.mocks['embeddings_output'] / 'vector_store_output').",
)
_d(
    "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
    "ai",
    vector_store_supabase.exec_vector_store_supabase,
    description="Supabase Vector Store — insert/load/retrieve LangChain documents against a (mocked) Supabase table. Honors parameters.mode ('insert'/'load'/'retrieve'), parameters.topK (default 4), parameters.tableName (default 'documents'), parameters.queryName (default 'match_documents'); resolves a connected embedding model via ai_embedding for the vector (mockable via ctx.mocks['embeddings_output'] / 'vector_store_output').",
)
_d(
    "@n8n/n8n-nodes-langchain.vectorStorePinecone",
    "ai",
    vector_store_pinecone.exec_vector_store_pinecone,
    description="Pinecone Vector Store — insert/load/retrieve LangChain documents against a (mocked) Pinecone index. Honors parameters.mode ('insert'/'load'/'retrieve'), parameters.topK (default 4), parameters.indexName (default 'n8n-vector-store'), parameters.namespace (default ''); resolves a connected embedding model via ai_embedding for the vector (mockable via ctx.mocks['embeddings_output'] / 'vector_store_output').",
)
_d(
    "@n8n/n8n-nodes-langchain.vectorStoreQdrant",
    "ai",
    vector_store_qdrant.exec_vector_store_qdrant,
    description="Qdrant Vector Store — insert/load/retrieve LangChain documents against a (mocked) Qdrant collection. Honors parameters.mode ('insert'/'load'/'retrieve'), parameters.topK (default 4), parameters.collectionName (default 'n8n-qdrant-collection'), parameters.url (default 'http://localhost:6333', echoed only); resolves a connected embedding model via ai_embedding for the vector (mockable via ctx.mocks['embeddings_output'] / 'vector_store_output').",
)
_d(
    "@n8n/n8n-nodes-langchain.vectorStorePGVector",
    "ai",
    vector_store_pgvector.exec_vector_store_pgvector,
    description="PGVector Vector Store — insert/load/retrieve LangChain documents against a (mocked) Postgres+pgvector table. Honors parameters.mode ('insert'/'load'/'retrieve'), parameters.topK (default 4), parameters.tableName (default 'n8n_pgvector_embeddings'), parameters.distanceStrategy (default 'cosine'); resolves a connected embedding model via ai_embedding for the vector (mockable via ctx.mocks['embeddings_output'] / 'vector_store_output').",
)
_d(
    "@n8n/n8n-nodes-langchain.mcpClientTool",
    "ai",
    llm_agent.exec_mcp_tool_stub,
    description="MCP Client Tool sub-node (HTTP endpointUrl or stub).",
)
_d(
    "@n8n/n8n-nodes-langchain.informationExtraction",
    "ai",
    text_ai.exec_information_extraction,
    description="Information Extraction — extract structured fields from text per parameters.schema (dict or list of field names); emits {text, extracted, schema, model, source} per item (mockable via ctx.mocks['extraction_output']; offline returns a stub dict with each field).",
)
_d(
    "@n8n/n8n-nodes-langchain.textClassifier",
    "ai",
    text_ai.exec_text_classifier,
    description="Text Classifier — classify text into one of parameters.categories (default positive/negative/neutral); emits {text, category, confidence, categories, model, source} per item (mockable via ctx.mocks['classification_output']; offline uses a positive/negative keyword heuristic, else neutral).",
)
_d(
    "@n8n/n8n-nodes-langchain.sentimentAnalysis",
    "ai",
    text_ai.exec_sentiment_analysis,
    description="Sentiment Analysis — return {label, confidence, model, source} for input text (mockable via ctx.mocks['sentiment_output']; offline uses a positive/negative keyword heuristic with neutral fallback).",
)
_d(
    "n8n-nodes-mcp.mcpClientTool",
    "ai",
    llm_agent.exec_mcp_tool_stub,
    description="Legacy MCP Client Tool sub-node (same stub executor).",
)

# ── Flow control (Tier A core engine gaps) ───────────────────────────
_d(
    "n8n-nodes-base.wait",
    "logic",
    flow.exec_wait,
    description="Wait / delay before continuing (seconds/minutes/hours/days).",
)
_d(
    "n8n-nodes-base.merge",
    "logic",
    flow.exec_merge,
    description="Merge multiple incoming streams (append / combineByPosition / chooseBranch).",
)
_d(
    "n8n-nodes-base.switch",
    "logic",
    flow.exec_switch,
    description="Switch — route items to one of N outputs by rule.",
)
_d(
    "n8n-nodes-base.limit",
    "transform",
    flow.exec_limit,
    description="Limit — keep first/last N items.",
)
_d(
    "n8n-nodes-base.removeDuplicates",
    "transform",
    flow.exec_remove_duplicates,
    description="Remove duplicate items by field comparison.",
)
_d(
    "n8n-nodes-base.sort",
    "transform",
    flow.exec_sort,
    description="Sort items by one or more fields (ascending/descending).",
)
_d(
    "n8n-nodes-base.compareDatasets",
    "transform",
    flow.exec_compare_datasets,
    outputs=("equal_items", "different_items", "unique_to_input_1", "unique_to_input_2"),
    description="Compare two input streams; bucket by equal / different / unique.",
)
_d(
    "n8n-nodes-base.noOp",
    "logic",
    flow.exec_noop,
    description="No-op — passes items through unchanged.",
)
_d(
    "n8n-nodes-base.stopAndError",
    "logic",
    flow.exec_stop_and_error,
    description="Stop the workflow with a configured error message.",
)
_d(
    "n8n-nodes-base.executeWorkflow",
    "logic",
    flow.exec_execute_workflow,
    description="Execute another workflow and return its primary output.",
)
_d(
    "n8n-nodes-base.stickyNote",
    "logic",
    flow.exec_sticky_note,
    description="UI-only sticky note (no runtime side effects).",
)
_d(
    "n8n-nodes-base.webhook",
    "trigger",
    flow.exec_webhook,
    description="Webhook trigger — start a run on inbound HTTP request.",
)
_d(
    "n8n-nodes-base.respondToWebhook",
    "output",
    flow.exec_respond_to_webhook,
    description="Respond to Webhook — capture response for the inbound HTTP call.",
)

# ── AI: memory + output parser sub-nodes (Tier D) ───────────────────
_d(
    "@n8n/n8n-nodes-langchain.memoryBufferWindow",
    "ai",
    ai_memory.exec_memory_buffer_window,
    description="Window Buffer Memory — sliding recent-message history for the agent.",
)
_d(
    "@n8n/n8n-nodes-langchain.outputParserStructured",
    "ai",
    ai_memory.exec_output_parser_structured,
    description="Structured Output Parser — extract JSON fields from the LLM response.",
)
_d(
    "@n8n/n8n-nodes-langchain.openAi",
    "ai",
    openai.exec_openai,
    description="OpenAI actions node — textCompletion, imageGeneration (DALL·E), transcription (Whisper), analyzeImage (vision). Mockable via ctx.mocks['openai'] keyed by operation.",
)
_d(
    "@n8n/n8n-nodes-langchain.agentThink",
    "ai",
    agent_tools.exec_agent_think,
    description="Agent Think — passthrough thinking/reasoning step. Mockable via ctx.mocks['think_output'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentCalculator",
    "ai",
    agent_tools.exec_agent_calculator,
    description="Agent Calculator — safe-eval math expression (AST walker, no imports). Mockable via ctx.mocks['calculator_output'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentCode",
    "ai",
    agent_tools.exec_agent_code,
    description="Agent Code — fenced preview of a JS/Python snippet (never executed). Mockable via ctx.mocks['code_output'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentHttp",
    "ai",
    agent_tools.exec_agent_http,
    description="Agent HTTP — mock-first HTTP request (url/method/headers/body). Mockable via ctx.mocks['http_response'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentWikipedia",
    "ai",
    agent_tools.exec_agent_wikipedia,
    description="Agent Wikipedia — search query returning [{title, snippet, url}] (offline stub). Mockable via ctx.mocks['wikipedia_output'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentWorkflow",
    "ai",
    agent_tools.exec_agent_workflow,
    description="Agent Workflow — invoke another workflow by id (synthetic offline record). Mockable via ctx.mocks['workflow_output'].",
)
_d(
    "@n8n/n8n-nodes-langchain.agentSerpApi",
    "ai",
    agent_tools.exec_agent_serpapi,
    description="Agent SerpApi — search returning 5 results (offline stub). Mockable via ctx.mocks['serp_output'] or ctx.mocks['serpapi_output'].",
)

# ── Binary / file utility nodes (List B) ────────────────────────────
_d(
    "n8n-nodes-base.itemLists",
    "transform",
    binary.exec_item_lists,
    description="Item Lists (legacy) — split/aggregate/flatten item collections.",
)
_d(
    "n8n-nodes-base.moveBinaryData",
    "transform",
    binary.exec_move_binary_data,
    description="Move Binary Data — convert between JSON and binary representations.",
)
_d(
    "n8n-nodes-base.readBinaryFile",
    "transform",
    binary.exec_read_binary_file,
    description="Read Binary File — read a single file from disk into binary data.",
)
_d(
    "n8n-nodes-base.readBinaryFiles",
    "transform",
    binary.exec_read_binary_files,
    description="Read Binary Files — read multiple files from a directory into binary data.",
)
_d(
    "n8n-nodes-base.writeBinaryFile",
    "transform",
    binary.exec_write_binary_file,
    description="Write Binary File — write binary data to a file on disk.",
)
_d(
    "n8n-nodes-base.spreadsheetFile",
    "transform",
    binary.exec_spreadsheet_file,
    description="Spreadsheet File — read/write CSV and XLSX spreadsheet files.",
)
_d(
    "n8n-nodes-base.readPDF",
    "transform",
    binary.exec_read_pdf,
    description="Read PDF — extract text from a PDF file.",
)

# ── Utility / misc nodes (List B) ───────────────────────────────────
_d(
    "n8n-nodes-base.debugHelper",
    "transform",
    utility_extra.exec_debug_helper,
    description="Debug Helper — pass-through with logging.",
)
_d(
    "n8n-nodes-base.executeCommand",
    "transform",
    utility_extra.exec_execute_command,
    description="Execute Command — run a shell command (mock-first, never executed).",
)
_d(
    "n8n-nodes-base.n8n",
    "transform",
    utility_extra.exec_n8n,
    description="n8n (meta API) — get workflow/execution metadata.",
)
_d(
    "n8n-nodes-base.evaluation",
    "transform",
    utility_extra.exec_evaluation,
    description="Evaluation — evaluate LLM output against expected output.",
)
_d(
    "n8n-nodes-base.evaluationTrigger",
    "trigger",
    utility_extra.exec_evaluation_trigger,
    description="Evaluation Trigger — emit evaluation test cases.",
)
_d(
    "n8n-nodes-base.activationTrigger",
    "trigger",
    utility_extra.exec_activation_trigger,
    description="Activation Trigger — fires when workflow is activated.",
)
_d(
    "n8n-nodes-base.n8nTrigger",
    "trigger",
    utility_extra.exec_n8n_trigger,
    description="n8n Trigger — generic n8n system trigger.",
)
_d(
    "n8n-nodes-base.form",
    "trigger",
    utility_extra.exec_form,
    description="n8n Form — form page trigger emitting submissions.",
)
_d(
    "n8n-nodes-base.totp",
    "transform",
    utility_extra.exec_totp,
    description="TOTP — generate/validate time-based one-time passwords.",
)
_d(
    "n8n-nodes-base.ldap",
    "transform",
    utility_extra.exec_ldap,
    description="LDAP — search/add/modify/delete LDAP entries.",
)
_d(
    "n8n-nodes-base.iCalendar",
    "transform",
    utility_extra.exec_icalendar,
    description="iCalendar — parse .ics calendar data into events.",
)
_d(
    "n8n-nodes-base.quickChart",
    "transform",
    utility_extra.exec_quick_chart,
    description="Quick Chart — generate chart URLs/images.",
)
_d(
    "n8n-nodes-base.hackerNews",
    "transform",
    utility_extra.exec_hacker_news,
    description="Hacker News — fetch HN stories.",
)

# ── Email service nodes (List B) ────────────────────────────────────
_d(
    "n8n-nodes-base.sendGrid",
    "action",
    email_extra.exec_sendgrid,
    description="SendGrid — send email via SendGrid API.",
)
_d(
    "n8n-nodes-base.sendInBlue",
    "action",
    email_extra.exec_brevo,
    description="Brevo (Sendinblue) — send email via Brevo API.",
)
_d(
    "n8n-nodes-base.mailgun",
    "action",
    email_extra.exec_mailgun,
    description="Mailgun — send email via Mailgun API.",
)
_d(
    "n8n-nodes-base.mailchimp",
    "action",
    email_extra.exec_mailchimp,
    description="Mailchimp — newsletter / list member operations.",
)
_d(
    "n8n-nodes-base.mailjet",
    "action",
    email_extra.exec_mailjet,
    description="Mailjet — send email via Mailjet API.",
)
_d(
    "n8n-nodes-base.postmarkTrigger",
    "trigger",
    email_extra.exec_postmark_trigger,
    description="Postmark Trigger — fires on inbound Postmark email.",
)
_d(
    "n8n-nodes-base.emailReadImap",
    "trigger",
    email_extra.exec_email_read_imap,
    description="Email IMAP Trigger — polls an IMAP mailbox for new messages.",
)

# ── Messaging / notification nodes (List B) ─────────────────────────
_d(
    "n8n-nodes-base.mattermost",
    "action",
    messaging_extra.exec_mattermost,
    description="Mattermost — send messages to Mattermost channels.",
)
_d(
    "n8n-nodes-base.matrix",
    "action",
    messaging_extra.exec_matrix,
    description="Matrix — send messages to Matrix rooms.",
)
_d(
    "n8n-nodes-base.rocketchat",
    "action",
    messaging_extra.exec_rocket_chat,
    description="Rocket.Chat — send messages to Rocket.Chat channels.",
)
_d(
    "n8n-nodes-base.gotify",
    "action",
    messaging_extra.exec_gotify,
    description="Gotify — send push notifications via Gotify.",
)
_d(
    "n8n-nodes-base.pushover",
    "action",
    messaging_extra.exec_pushover,
    description="Pushover — send push notifications via Pushover.",
)
_d(
    "n8n-nodes-base.pushbullet",
    "action",
    messaging_extra.exec_pushbullet,
    description="Pushbullet — send pushes via Pushbullet.",
)
_d(
    "n8n-nodes-base.messageBird",
    "action",
    messaging_extra.exec_message_bird,
    description="MessageBird — send SMS/messages via MessageBird.",
)
_d(
    "n8n-nodes-base.sms77",
    "action",
    messaging_extra.exec_sms77,
    description="SMS77 — send SMS via SMS77.",
)

# ── Google extra nodes (List B) ─────────────────────────────────────
_d(
    "n8n-nodes-base.googleAnalytics",
    "action",
    google_extra.exec_google_analytics,
    description="Google Analytics — get GA reports.",
)
_d(
    "n8n-nodes-base.googleSlides",
    "action",
    google_extra.exec_google_slides,
    description="Google Slides — presentation operations.",
)
_d(
    "n8n-nodes-base.googleTasks",
    "action",
    google_extra.exec_google_tasks,
    description="Google Tasks — task operations.",
)
_d(
    "n8n-nodes-base.googleContacts",
    "action",
    google_extra.exec_google_contacts,
    description="Google Contacts — contact operations.",
)
_d(
    "n8n-nodes-base.googleTranslate",
    "action",
    google_extra.exec_google_translate,
    description="Google Translate — translate text.",
)
_d(
    "n8n-nodes-base.googleAds",
    "action",
    google_extra.exec_google_ads,
    description="Google Ads — ads query/report operations.",
)
_d(
    "n8n-nodes-base.googleBigQuery",
    "action",
    google_extra.exec_google_bigquery,
    description="Google BigQuery — query/insert/table operations.",
)
_d(
    "n8n-nodes-base.googleCloudStorage",
    "action",
    google_extra.exec_google_cloud_storage,
    description="Google Cloud Storage — GCS file operations.",
)
_d(
    "n8n-nodes-base.googleBusinessProfile",
    "action",
    google_extra.exec_google_business_profile,
    description="Google Business Profile — GBP operations.",
)
_d(
    "n8n-nodes-base.googleChat",
    "action",
    google_extra.exec_google_chat,
    description="Google Chat — chat message/space operations.",
)
_d(
    "n8n-nodes-base.gSuiteAdmin",
    "action",
    google_extra.exec_g_suite_admin,
    description="G Suite Admin — admin directory operations.",
)

# ── Project tracker nodes (List B) ──────────────────────────────────
_d(
    "n8n-nodes-base.clickUp",
    "action",
    trackers.exec_clickup,
    description="ClickUp — task operations.",
)
_d("n8n-nodes-base.trello", "action", trackers.exec_trello, description="Trello — card operations.")
_d("n8n-nodes-base.asana", "action", trackers.exec_asana, description="Asana — task operations.")
_d(
    "n8n-nodes-base.mondayCom",
    "action",
    trackers.exec_monday,
    description="Monday.com — item operations.",
)
_d(
    "n8n-nodes-base.todoist",
    "action",
    trackers.exec_todoist,
    description="Todoist — task operations.",
)
_d(
    "n8n-nodes-base.linear",
    "action",
    trackers.exec_linear,
    description="Linear — issue operations.",
)

# ── DevOps integration nodes (List B) ───────────────────────────────
_d("n8n-nodes-base.gitlab", "action", devops.exec_gitlab, description="GitLab — issue/MR operations.")
_d("n8n-nodes-base.gitlabTrigger", "trigger", devops.exec_gitlab_trigger, description="GitLab Trigger — emit one item per received GitLab webhook event (mockable via ctx.mocks['gitlab_trigger_payload'] / 'trigger_payload'; offline fallback synthesizes a {event, projectId, objectKind, source: 'gitlab'} payload).")

_d("n8n-nodes-base.bitbucketTrigger", "trigger", devops.exec_bitbucket_trigger, description="Bitbucket Trigger — emit one item per received Bitbucket webhook event (mockable via ctx.mocks['bitbucket_trigger_payload'] / 'trigger_payload'; offline fallback synthesizes a {event, repository, actor, source: 'bitbucket'} payload).")
_d("n8n-nodes-base.jenkins", "action", devops.exec_jenkins, description="Jenkins — job/build operations.")
_d("n8n-nodes-base.circleCi", "action", devops.exec_circleci, description="CircleCI — pipeline/workflow/job operations.")

# ── Microsoft extra nodes (List B) ───────────────────────────────────
_d("n8n-nodes-base.microsoftExcel", "action", microsoft_extra.exec_microsoft_excel, description="Microsoft Excel — read/append/update/delete Excel rows.")
_d("n8n-nodes-base.microsoftOneDrive", "action", microsoft_extra.exec_microsoft_onedrive, description="Microsoft OneDrive — file operations.")
_d("n8n-nodes-base.microsoftSharePoint", "action", microsoft_extra.exec_microsoft_sharepoint, description="Microsoft SharePoint — file/list operations.")
_d("n8n-nodes-base.microsoftSql", "action", microsoft_extra.exec_microsoft_sql, description="Microsoft SQL — execute SQL queries.")
_d("n8n-nodes-base.microsoftEntra", "action", microsoft_extra.exec_microsoft_entra, description="Microsoft Entra — Azure AD user/group operations.")
_d("n8n-nodes-base.microsoftToDo", "action", microsoft_extra.exec_microsoft_todo, description="Microsoft To Do — task operations.")
