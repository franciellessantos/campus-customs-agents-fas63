# Campus Customs — Agent Team Desk (HW5)

A five-agent team that runs Campus Customs, a shop selling Yale merchandise to students and parents. It has three linked pieces:

| Piece | Folder | What it does |
|---|---|---|
| MCP server (FastMCP) | `mcp_server/` | 13 tools that read and update the shop database. Every agent works only through these tools. |
| Backend (FastAPI + PydanticAI) | `backend/` | Boss, Inventory, Accounting, Facilities and Customer Service agents, fully connected, plus the API routes. |
| Dashboard (React + Vite + TypeScript) | `frontend/` | Lets a human watch the agents work, approve payments and purchases, and track cash. |

**Model:** every agent uses `gpt-6-luna` through Portkey (OpenAI Responses API). It's set once in `backend/main.py` (`MODEL_NAME`).

**Safety:** agents can only *request* payments. Money moves only when a human clicks Approve, and the payment is refused if checking would go negative. Customer messages and purchase orders are drafts and are never sent.

---

## 1. Setup (once)

```bash
pip install -r requirements.txt
```

```bash
cd frontend && npm install
```

Create your `.env` from the placeholder and paste your own Portkey key. **Never commit `.env`.**

```bash
cp .env.example .env
```

Download the shop data from https://zlisto.github.io/mgt_409_fa26/data/hw5/data.zip and unzip it so that `data/campus_customs.db` exists. The databases are not in this repository.

## 2. Copy the original database to the working copy (needed for every new run)

`data/campus_customs.db` is the **original**. It is never written to and is kept for audits and resets. Everything (MCP server, backend, agents) reads and writes the **working copy** `data/campus_customs_new.db`.

Before your first run, or any time you want a clean start, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

(On Windows PowerShell: `Copy-Item data\campus_customs.db data\campus_customs_new.db -Force`.) Once the backend is running, the **Reset database** button or `POST /reset` does the same thing (see step 6).

## 3. Start the MCP server

Run from the repository root:

```bash
python mcp_server/server.py
```

This starts the `campus-customs` server over stdio, which is useful for testing it alone. You normally don't need to start it by hand:
- The backend launches it automatically for every agent run.
- Claude Code and other MCP clients start it from `.mcp.json`.

The server creates two work tables (`approvals`, `drafts`) in the working copy only. See `mcp_server/README.md` for the tool list.

## 4. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The backend is now at http://localhost:8000 (http://localhost:8000/docs lists every route). It allows the Vite page at http://localhost:5173.

| Route | What it does |
|---|---|
| `GET /tickets` | Tickets with status, live run meter, and the Boss's final call |
| `POST /tickets/{id}/run` · `POST /tickets/{id}/stop` | Start or stop the agent team on one ticket |
| `GET /events` | What each agent said, who it delegated to, and which tools it used |
| `GET /approvals` | Pending and decided payments, purchase orders and message drafts |
| `POST /approvals/{id}/approve` · `/reject` | Human decision on a payment (the only route that moves cash) |
| `POST /drafts/{id}/approve` · `/reject` | Human decision on a purchase order or message (nothing is sent) |
| `GET /cash` · `GET /transactions` · `GET /payables` | Checking balance, payment history, accounts payable |
| `GET /runs` | Tokens and estimated AI cost per run (never charged to checking) |
| `POST /reset` | Stop any run and restore the original database |

## 5. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

This opens http://localhost:5173. Choose a ticket and press **▶ Play**. Approval banners block the screen until you Approve, Decline or Close them; if cash can't cover a request, only Decline is allowed.

## 6. Reset the database before a full three-ticket run

Always start a full run of tickets 101, 102 and 103 from the original data:

1. Click **Reset database** on the board, or run:
   ```bash
   curl -X POST http://localhost:8000/reset
   ```
   This stops any running team and restores `campus_customs.db` into `campus_customs_new.db` (checking back to $3,400, all tickets open). Steps 2 and 6 do the same thing; use step 2 when the backend isn't running.
2. Play tickets **101**, **102** and **103**.
3. Decide each approval banner. Every run, human decision and reset is appended to `output/audit_trail.json`.

---

## Outputs (`output/`)

| File | Contents |
|---|---|
| `harness.md` | Tables, MCP tools, agents, routes, dashboard and safety rules, built up problem by problem |
| `mcp_smoke.json` | Live test of the first three MCP tools against the database |
| `desk_tickets.html` | Expected vs actual for each ticket, a cash walk-through and reflections (double-click to open) |
| `design.md` | Dashboard design changes |
| `resolved_tickets.json` | Final status, outcome, agent work and human approvals per ticket |
| `resolved_board.html` | Screenshots of the board after each ticket (double-click to open) |
| `audit_trail.json` | Append-only log of real runs, human decisions and resets |
| `github_url.txt` | Link to this repository |

`AI_prompts.md` logs every prompt used to build the project.
