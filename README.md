# obsidian-vault-mcp

A personal **Model Context Protocol** server for an Obsidian vault, paired with a multi-agent organizer that proactively links and tags your notes on a schedule. Backed by Deep Agents + LangSmith, fronted by a small Next.js UI, deployed on Vercel.

```
┌──────────────┐    ┌────────────────┐    ┌────────────────────┐
│  Next.js UI  │───▶│  FastAPI       │───▶│  Obsidian MCP      │
│  AI Gateway  │    │  /chat /cron   │    │  (FastMCP)         │
└──────────────┘    └────────┬───────┘    └─────────┬──────────┘
                             │                      │
                     ┌───────▼────────┐     ┌───────▼────────┐
                     │  Deep Agents   │     │  Vault on disk │
                     │  + LangSmith   │     │  (filesystem)  │
                     └────────────────┘     └────────────────┘
```

The MCP server talks to the vault **directly from disk** — no plugin, no API key, just `VAULT_PATH=/path/to/your/vault`.

---

## 1. Prerequisites

| Tool | Why | Install |
|---|---|---|
| `uv` ≥ 0.5 | Python workspace manager | `brew install uv` |
| `node` ≥ 20 | Next.js | `brew install node` (or fnm/nvm) |
| `gh` | GitHub CLI for the deploy flow | `brew install gh` |
| `vercel` | Deployment | `npm i -g vercel` |
| An Obsidian vault | Any directory of `.md` files | — |

An **LLM API key** of your choice (one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`) or a **Vercel AI Gateway key** for the UI chat.

---

## 2. Local setup

```bash
git clone git@github.com:Shumatsurontek/obsidian-vault-mcp.git
cd obsidian-vault-mcp

cp .env.example .env
# Edit .env: set at minimum VAULT_PATH and one LLM key

make install                      # uv sync --all-packages
npm --prefix web install
```

Run the three services (separate terminals):

```bash
make run-mcp-http   # MCP on :8000   (HTTP for the agents/UI)
make run-api        # FastAPI on :3001
make run-web        # Next.js on :3000
```

Open <http://localhost:3000>.

---

## 3. Connect to **Claude Code / Claude Desktop** (local stdio)

Add this to `~/.config/claude/claude_desktop_config.json` (macOS path) or your Claude Code MCP config:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "uv",
      "args": ["run", "--package", "obsidian-mcp", "obsidian-mcp"],
      "cwd": "/absolute/path/to/obsidian-vault-mcp",
      "env": {
        "VAULT_PATH": "/absolute/path/to/your/Obsidian/Vault"
      }
    }
  }
}
```

Restart the client. You'll see 12 tools available: `vault_list`, `vault_read`, `vault_write`, `vault_append`, `vault_delete`, `vault_set_frontmatter`, `list_all_notes`, `search_simple`, `list_outgoing_links`, `find_link_candidates`, `add_wikilink`, `find_backlinks`.

### Quick test prompts inside Claude

> "List the top-level folders in my vault."
> "Find notes that mention 'Atlas' and propose 2 wikilinks I should add."
> "Add a #project tag to `Inbox/note-un.md` and link it to `Atlas`."

---

## 4. Connect to **any other MCP client** (HTTP)

For ChatGPT, Cursor, custom agents — point them at the streamable-HTTP endpoint:

```
URL:     http://127.0.0.1:8000/mcp
Method:  streamable_http
```

For remote access (e.g. ChatGPT custom connector), tunnel it:

```bash
# Example with cloudflared
cloudflared tunnel --url http://127.0.0.1:8000
```

> Auth is currently single-user. Set `MCP_STATIC_TOKEN=<random>` in `.env` and add `Authorization: Bearer <token>` headers from your client.

---

## 5. Deploy on Vercel

The Next.js UI + FastAPI backend deploy on Vercel. The MCP server itself stays local (it needs your filesystem); the deployed UI calls the local MCP via the FastAPI proxy.

```bash
vercel link
vercel env pull                   # pull whatever you've set in Vercel into .env.local
vercel deploy                     # preview
vercel deploy --prod              # promote
```

`vercel.json` schedules a cron at `0 */6 * * *` that hits `/api/cron/organize` (protected by `CRON_SECRET`).

> ⚠️ **Cron + remote vault**: a Vercel function can't read your local filesystem. For the proactive organizer to run remotely you need either (a) a Git-synced vault the function clones, or (b) keep the cron local via `launchd`/`systemd` and use Vercel only for the UI. The local-only path is the simplest and works today.

---

## 6. Layout

```
.
├── shared/          # tracing (JSON events), identity, logging
├── obsidian_mcp/    # FastMCP server, filesystem backend
├── agents/          # Deep Agents orchestrator + linker/tagger sub-agents
├── api/             # FastAPI backend (chat + cron endpoints)
├── web/             # Next.js 16 front-end (AI SDK v6 + AI Gateway)
├── vercel.json
├── Makefile
└── pyproject.toml   # UV workspace root
```

---

## 7. Environment variables

| Key | Required | Notes |
|---|---|---|
| `VAULT_PATH` | ✅ | Absolute path to the Obsidian vault directory |
| `ANTHROPIC_API_KEY` *(or other)* | ✅ | At least one LLM provider for the agents |
| `AI_GATEWAY_API_KEY` | for UI streaming | Vercel AI Gateway key |
| `AI_GATEWAY_MODEL` | default `anthropic/claude-opus-4-7` | Any `provider/model` string |
| `AGENT_MODEL` | default `anthropic:claude-opus-4-7` | LangChain `init_chat_model` spec |
| `MCP_URL` | default `http://127.0.0.1:8000/mcp` | How the agents reach the MCP server |
| `MCP_STATIC_TOKEN` | optional | Bearer token for remote MCP access |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | optional | Agent trace export |
| `CRON_SECRET` | for prod | Protects `/api/cron/organize` |

---

## 8. Common commands

```bash
make install                  # uv sync --all-packages
make run-mcp                  # stdio mode (for Claude Desktop/Code)
make run-mcp-http             # HTTP mode (for agents/remote)
make run-api                  # FastAPI dev server
make run-web                  # Next.js dev server
make test                     # pytest
make lint                     # ruff check
make format                   # ruff format + fix
```

---

## 9. License

MIT — personal project.
