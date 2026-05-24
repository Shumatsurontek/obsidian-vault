# obsidian-vault-mcp

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

- The MCP server (`obsidian_mcp`) exposes 29 tools over FastMCP, backed by a
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
| Links | `list_outgoing_links`, `find_backlinks`, `find_link_candidates`, `add_wikilink` |
| Graph | `move_note`, `find_orphans`, `find_unresolved_links`, `vault_stats`, `list_recent_notes` |
| Tags | `list_tags`, `get_notes_by_tag`, `get_frontmatter`, `rename_tag`, `merge_tags` |
| Templates | `list_templates`, `create_from_template`, `upsert_template`, `create_daily_note` |
| Semantic | `semantic_search`, `find_similar_notes`, `reindex_embeddings` |

Notes on behavior:

- `move_note` rewrites every `[[wikilink]]` that targets the note, including
  `|alias` and `#heading` forms, so references are not broken. Prefer it over
  delete-and-recreate.
- Semantic tools build an embedding index cached at `<vault>/.vault-mcp/`,
  keyed by file modification time, so refreshes only re-embed changed notes.
  They are disabled and return an explicit error when `OPENAI_API_KEY` is unset.
- Template and daily-note directories are auto-detected by name when
  `OBSIDIAN_TEMPLATES_DIR` / `OBSIDIAN_DAILY_DIR` are not set.

Example client prompts:

```
Report vault_stats and list orphan notes.
Semantic-search for "prompt caching strategies" and read the top result.
Find notes similar to 00-inbox/TODO GAIA.md and propose two wikilinks.
List tags with counts, then merge "infra" and "infrastructure" into "infrastructure".
Move "Inbox/note-un.md" to "Projects/Note Un.md" and fix all backlinks.
Create today's daily note from the daily template.
```

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
| `MCP_STATIC_TOKEN` | optional | Bearer token for remote MCP access |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | optional | Agent trace export |
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
