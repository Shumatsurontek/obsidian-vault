# obsidian-vault-mcp

[![CI](https://github.com/Shumatsurontek/obsidian-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/Shumatsurontek/obsidian-vault/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<!-- Demo: record a short GIF of the organizer linking notes, save as docs/demo.gif, then uncomment:
![Vault organizer in action](docs/demo.gif)
-->

A Model Context Protocol (MCP) server for an Obsidian vault, paired with a
multi-agent organizer that links, tags, and restructures notes on a schedule.
The server reads and writes the vault directly from the filesystem; no plugin
and no API key are required to operate it.

## Architecture

```
┌──────────────┐    ┌────────────────┐    ┌────────────────────┐
│  Next.js UI  │───▶│  FastAPI       │───▶│  Obsidian MCP      │
│  AI Gateway  │    │  /chat /agent  │    │  (FastMCP)         │
└──────────────┘    │  /cron         │    └─────────┬──────────┘
                    └────────┬───────┘              │
                             │                      │
                     ┌───────▼────────┐     ┌───────▼────────┐
                     │  Deep Agents   │     │  Vault on disk │
                     │  + LangSmith   │     │  (filesystem)  │
                     └────────────────┘     └────────────────┘
```

- The MCP server (`obsidian_mcp`) exposes 35 tools over FastMCP, backed by a
  path-safe filesystem client. Configuration is a single variable,
  `VAULT_PATH`.
- The agent layer (`agents`) is a Deep Agents orchestrator with `linker` and
  `tagger` sub-agents. It consumes the MCP tools through
  `langchain-mcp-adapters` and emits traces to LangSmith.
- The backend (`api`) is a FastAPI app exposing a streaming chat endpoint and a
  cron-protected organizer endpoint.
- The frontend (`web`) is a Next.js application that streams chat from the agent
  and triggers organizer passes.

## Components

| Package | Role |
|---|---|
| `shared` | Tool-call tracing (JSON events to stderr), identity extraction, logging |
| `obsidian_mcp` | FastMCP server, filesystem-backed vault client |
| `agents` | Deep Agents orchestrator and conversational chat agent |
| `api` | FastAPI backend (`/api/chat`, `/api/agent`, `/api/cron/organize`) |
| `web` | Next.js frontend (AI SDK v6, Vercel AI Gateway) |

## Requirements

| Tool | Purpose | Install |
|---|---|---|
| `uv` >= 0.5 | Python workspace manager | `brew install uv` |
| `node` >= 20 | Next.js frontend | `brew install node` |
| `gh` | GitHub CLI | `brew install gh` |
| `vercel` | Deployment (optional) | `npm i -g vercel` |

At least one LLM provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or
`GOOGLE_API_KEY`) is required for the agents. `OPENAI_API_KEY` additionally
enables the semantic search tools.

## Local setup

```bash
git clone git@github.com:Shumatsurontek/obsidian-vault-mcp.git
cd obsidian-vault-mcp

cp .env.example .env       # set VAULT_PATH and at least one LLM key
make install               # uv sync --all-packages
npm --prefix web install
```

Run the services in separate terminals:

```bash
make run-mcp-http          # MCP server on :8000
make run-api               # FastAPI on :3001
make run-web               # Next.js on :3000
```

The UI is served at http://localhost:3000.

## Connecting an MCP client

### Claude Code / Claude Desktop (stdio)

The recommended path is the Claude Code CLI with user scope, which makes the
server available in every project:

```bash
claude mcp add obsidian-vault -s user \
  --env VAULT_PATH=/absolute/path/to/your/Obsidian/Vault \
  --env OPENAI_API_KEY=sk-...   \
  -- uv run --directory /absolute/path/to/obsidian-vault-mcp --package obsidian-mcp obsidian-mcp
```

Equivalent manual configuration (`~/.claude.json` for Claude Code,
`~/.config/claude/claude_desktop_config.json` for Desktop):

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/obsidian-vault-mcp", "--package", "obsidian-mcp", "obsidian-mcp"],
      "env": {
        "VAULT_PATH": "/absolute/path/to/your/Obsidian/Vault",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

`OPENAI_API_KEY` is optional and only required for the semantic tools.

### Other clients (HTTP)

Point any streamable-HTTP MCP client at the running server:

```
URL:     http://127.0.0.1:8000/mcp
Method:  streamable_http
```

For remote access, expose the local server through a tunnel (for example
`cloudflared tunnel --url http://127.0.0.1:8000`). Authentication is single-user:
set `MCP_STATIC_TOKEN` and send `Authorization: Bearer <token>` from the client.

## Tools

| Family | Tools |
|---|---|
| Vault | `vault_list`, `vault_read`, `vault_write`, `vault_append`, `vault_delete`, `vault_set_frontmatter`, `list_all_notes`, `search_simple` |
| Links | `list_outgoing_links`, `find_backlinks`, `find_link_candidates`, `add_wikilink`, `remove_wikilink` |
| Graph | `move_note`, `find_orphans`, `find_unresolved_links`, `vault_stats`, `list_recent_notes`, `export_graph` |
| Tags | `list_tags`, `get_notes_by_tag`, `get_frontmatter`, `rename_tag`, `merge_tags` |
| Templates | `list_templates`, `create_from_template`, `upsert_template`, `create_daily_note` |
| Semantic | `semantic_search`, `find_similar_notes`, `find_duplicates`, `reindex_embeddings` |
| Snapshots | `snapshot_vault`, `list_snapshots`, `undo_last_pass` |

Notes on behavior:

- `add_wikilink` is idempotent (won't duplicate a link to a note already linked,
  case-insensitively) and appends to any `*Related*` heading without disturbing
  list spacing. `remove_wikilink` is its inverse — it strips a link (alias and
  `#heading` forms included) and cleans up the emptied bullet.
- `move_note` rewrites every `[[wikilink]]` that targets the note, including
  `|alias` and `#heading` forms, so references are not broken. Prefer it over
  delete-and-recreate. Link resolution is case-insensitive, matching Obsidian.
- Semantic tools build an embedding index cached at `<vault>/.vault-mcp/`,
  keyed by file modification time, so refreshes only re-embed changed notes.
  They are disabled and return an explicit error when `OPENAI_API_KEY` is unset.
- Snapshots are git-backed in an isolated git directory under `.vault-mcp/`;
  they never create a `.git` in the vault. **Every write auto-creates a restore
  point** at the client layer — consecutive edits within ~90s share one baseline,
  so `undo_last_pass` reverts a whole batch (an organizer pass, or a burst of
  manual edits) rather than just the last write.
- The organizer supports a dry-run mode (read-only) that proposes a reviewable
  change list without writing. The UI exposes it as a checkbox.
- `export_graph` returns the link graph as Mermaid or JSON; `find_duplicates`
  reports near-identical notes by embedding similarity.
- Template and daily-note directories are auto-detected by name when
  `OBSIDIAN_TEMPLATES_DIR` / `OBSIDIAN_DAILY_DIR` are not set.

Example client prompts:

```
Report vault_stats and list orphan notes.
Semantic-search for "prompt caching strategies" and read the top result.
Find notes similar to Inbox/reading-list.md and propose two wikilinks.
List tags with counts, then merge "infra" and "infrastructure" into "infrastructure".
Move "Inbox/note-un.md" to "Projects/Note Un.md" and fix all backlinks.
Create today's daily note from the daily template.
```

## Security

This server can **read, write, and delete** your vault. Treat access to it as
access to your notes.

- **stdio** transport (Claude Code / Desktop) is local-only and unauthenticated
  by design — the client launches the process directly.
- **HTTP/SSE** transport requires `Authorization: Bearer <MCP_STATIC_TOKEN>` on
  every request (the `/health` probe is public). If `MCP_STATIC_TOKEN` is unset
  the server still starts but logs a loud warning and runs **open** — never
  expose it on a network without a token. Tokens are compared in constant time.
- The FastAPI routes that trigger agent runs (`/api/chat`, `/api/agent`) require
  `Authorization: Bearer <API_SECRET>`; the Vercel cron route uses `CRON_SECRET`.
  Each guard is a no-op only when its secret is unset (local dev) — set them
  before deploying.
- Secrets live in `.env` (git-ignored), GitHub Actions secrets in CI, and the
  platform secret store in production. Never commit a real `.env`.
- Snapshots are stored in `<vault>/.vault-mcp/` and are excluded from the
  snapshot history itself; they are local restore points, not a backup.

## Deployment (Vercel)

The Next.js UI and FastAPI backend deploy to Vercel. The MCP server stays local
because it requires filesystem access to the vault; the deployed UI reaches the
agent through the FastAPI endpoints.

```bash
vercel link
vercel env pull
vercel deploy            # preview
vercel deploy --prod     # production
```

`vercel.json` registers a cron at `0 */6 * * *` that calls
`/api/cron/organize`, protected by `CRON_SECRET`.

A Vercel function cannot read a local filesystem. To run the organizer remotely,
either back the vault with a Git repository the function clones, or keep the
cron local (launchd / systemd) and use Vercel for the UI only.

## Environment variables

| Key | Required | Notes |
|---|---|---|
| `VAULT_PATH` | yes | Absolute path to the Obsidian vault |
| `OPENAI_API_KEY` | for semantic tools | Enables `semantic_search` / `find_similar_notes` |
| `OBSIDIAN_TEMPLATES_DIR`, `OBSIDIAN_DAILY_DIR` | optional | Vault-relative; auto-detected by name if empty |
| `OBSIDIAN_EMBEDDING_MODEL` | default `text-embedding-3-small` | Embedding model |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | one required | LLM provider for the agents |
| `AGENT_MODEL` | default `openai:gpt-5.4-mini` | LangChain `init_chat_model` spec |
| `AI_GATEWAY_API_KEY` | for UI streaming via gateway | Vercel AI Gateway key |
| `AI_GATEWAY_MODEL` | default `openai/gpt-5.4-mini` | `provider/model` string |
| `MCP_URL` | default `http://127.0.0.1:8000/mcp` | Agent-to-MCP endpoint |
| `MCP_STATIC_TOKEN` | for HTTP/SSE | Bearer token guarding the network MCP transport; server warns and runs open if unset |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | optional | Agent trace export |
| `API_SECRET` | for public deploy | Protects `/api/chat` and `/api/agent` |
| `CRON_SECRET` | production | Protects `/api/cron/organize` |

## Make targets

```bash
make install        # uv sync --all-packages
make run-mcp        # MCP server, stdio transport
make run-mcp-http   # MCP server, HTTP transport
make run-api        # FastAPI dev server
make run-web        # Next.js dev server
make test           # pytest
make lint           # ruff check
make format         # ruff format + fix
```

## License

MIT
