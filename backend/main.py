"""Campus Customs backend: settings, the five-agent team, and the FastAPI routes for the dashboard.

Run from backend/:  uvicorn main:app --reload --port 8000
MODEL: every agent uses gpt-6-luna through Portkey (MODEL_NAME below). There is no fallback model.

The team (PydanticAI) is fully connected: every agent has `ask_teammate`, so any agent can delegate
to any other one, and each gets only the MCP tools its role needs (mcp_server/server.py).
`execute_payment` goes to NO agent. Agents only *request* payments; the approve route is the only
place money moves: a human click marks the approval as approved, then the MCP `execute_payment`
tool pays it, refusing if checking does not have enough cash. Approved purchase orders are not
paid now; they become accounts payable, due on delivery.
"""

import asyncio
import json
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

from models import AgentName, AgentReply, TeamDeps, TicketResolution, TraceEvent

# ===================== Settings =====================

HW5_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = HW5_DIR.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MCP_SERVER = HW5_DIR / "mcp_server" / "server.py"
ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"
WORKING_DB = HW5_DIR / "data" / "campus_customs_new.db"

MODEL_NAME = "gpt-6-luna"

# ASSUMED gpt-6-luna list prices (USD per 1M tokens) for the cost ESTIMATE shown on the dashboard.
# Accountability only: this is never deducted from the shop's checking balance.
# Update these if Portkey shows different prices for gpt-6-luna.
PRICE_INPUT_PER_1M = 1.25
PRICE_OUTPUT_PER_1M = 10.00

# hw5/.env when cloned on its own; falls back to the course-folder .env.
load_dotenv(HW5_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")


def build_model() -> OpenAIResponsesModel:
    """OpenAI Responses API routed through Portkey, pinned to gpt-6-luna."""
    key = os.environ["PORTKEY_API_KEY"]
    client = AsyncOpenAI(
        api_key=key,
        base_url="https://api.portkey.ai/v1",
        default_headers={
            "x-portkey-api-key": key,
            "x-portkey-provider": "openai",
            # Always a fresh model answer: a cached reply would not be a real agent run.
            "x-portkey-cache-force-refresh": "true",
        },
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))

# Agent work tables, same definition as in mcp_server/server.py (used when resetting the database).
WORK_TABLES_SQL = """CREATE TABLE IF NOT EXISTS approvals (
                   id INTEGER PRIMARY KEY,
                   kind TEXT NOT NULL,                      -- 'invoice' or 'rent'
                   ref_id INTEGER NOT NULL,
                   amount REAL NOT NULL,
                   reason TEXT NOT NULL,
                   requested_by TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/paid/refused
                   decided_by TEXT,
                   result TEXT,
                   created_at TEXT NOT NULL
               );
               CREATE TABLE IF NOT EXISTS drafts (
                   id INTEGER PRIMARY KEY,
                   kind TEXT NOT NULL,                      -- 'purchase_order' or 'customer_message'
                   ticket_id INTEGER,
                   author TEXT NOT NULL,
                   payload TEXT NOT NULL,                   -- JSON
                   status TEXT NOT NULL DEFAULT 'draft',    -- draft/approved/rejected (set by a human)
                   decided_by TEXT,
                   created_at TEXT NOT NULL
               );"""


# ===================== Agent team =====================

TOOLS_BY_AGENT: dict[AgentName, set[str]] = {
    "boss": {"get_ticket", "list_open_tickets", "update_ticket"},
    "inventory": {"get_ticket", "check_stock", "list_vendors", "get_invoice_status", "draft_purchase_order"},
    "accounting": {"get_ticket", "check_stock", "get_invoice_status", "get_lease_and_cash", "get_cash_balance", "list_vendors",
                   "list_payments_and_approvals", "request_payment_approval"},
    "facilities": {"get_ticket", "get_lease_and_cash", "get_cash_balance"},
    "customer_service": {"get_ticket", "draft_customer_message"},
}

ROLES: dict[AgentName, str] = {
    "boss": "reads tickets, shares the work evenly, makes the final call",
    "inventory": "stock by SKU and size, shortfalls, restock vendor, purchase order drafts",
    "accounting": "cash, invoices, margins, discounts, payment approval requests",
    "facilities": "shop space, lease and rent",
    "customer_service": "drafts messages to customers and the landlord",
}

def mcp_client() -> Client:
    # Same launch command as the project-root .mcp.json (system python has fastmcp server support).
    return Client(StdioTransport(command="python", args=[str(MCP_SERVER)]))


async def log_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, tool_args: dict):
    """Record every MCP tool call (which agent, which tool, what came back) for the dashboard."""
    agent = ctx.deps.stack[-1]
    ctx.deps.log(agent, "tool", f"{name}({json.dumps(tool_args)})", tool=name)
    result = await call_tool(name, tool_args)
    ctx.deps.log(agent, "tool_result", str(result)[:600], tool=name)
    return result


mcp_toolset = MCPToolset(mcp_client(), process_tool_call=log_tool_call)
model = build_model()


def scoped_tools(name: AgentName):
    allowed = TOOLS_BY_AGENT[name]
    return mcp_toolset.filtered(lambda ctx, tool: tool.name in allowed)


def make_agent(name: AgentName) -> Agent:
    agent = Agent(
        model,
        name=name,
        deps_type=TeamDeps,
        output_type=TicketResolution if name == "boss" else AgentReply,
        instructions=(PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"),
        toolsets=[scoped_tools(name)],
        retries=2,
    )

    @agent.instructions
    def context(ctx: RunContext[TeamDeps]) -> str:
        team = "\n".join(f"- {n}: {r}" for n, r in ROLES.items() if n != name)
        return (f"You are '{name}'. Current ticket: {ctx.deps.ticket_id}.\n"
                f"Teammates you can ask with ask_teammate:\n{team}")

    @agent.tool
    async def ask_teammate(ctx: RunContext[TeamDeps], teammate: AgentName, task: str) -> str:
        """Delegate a task to any teammate and get their answer back."""
        return await delegate(ctx, name, teammate, task)

    if name == "boss":
        @agent.tool
        def team_workload(ctx: RunContext[TeamDeps]) -> dict[str, int]:
            """How many tasks each specialist has received so far, to share work evenly."""
            return {n: ctx.deps.workload.get(n, 0) for n in ROLES if n != "boss"}

    return agent


async def delegate(ctx: RunContext[TeamDeps], sender: AgentName, teammate: AgentName, task: str) -> str:
    deps = ctx.deps
    if teammate == sender:
        return "You cannot delegate to yourself."
    if teammate == "boss":
        return "Don't send work back to the Boss. Answer with what you have and list open questions in concerns."
    if sum(deps.workload.values()) >= deps.max_delegations:
        return f"Team delegation budget ({deps.max_delegations}) used up. Answer with what you have."
    if deps.depth >= deps.max_depth:
        return f"Delegation limit ({deps.max_depth} levels) reached. Answer with what you have."
    deps.log(sender, "delegate", task, target=teammate)
    deps.workload[teammate] = deps.workload.get(teammate, 0) + 1
    # Each delegation gets its own stack/depth (parallel calls stay correctly attributed);
    # trace and workload are shared by reference.
    child = replace(deps, depth=deps.depth + 1, stack=[*deps.stack, teammate])
    try:
        result = await AGENTS[teammate].run(task, deps=child, usage=ctx.usage)
        reply = result.output
        deps.log(teammate, "reply", reply.summary, target=sender)
        return reply.model_dump_json()
    except Exception as exc:
        deps.log(teammate, "error", str(exc), target=sender)
        return f"{teammate} failed: {exc}"


AGENTS: dict[AgentName, Agent] = {name: make_agent(name) for name in ROLES}


async def run_ticket(ticket_id: int, trace: list | None = None,
                     usage: RunUsage | None = None) -> tuple[TicketResolution, TeamDeps]:
    """Agent loop for one ticket: the Boss delegates and the team works until the Boss makes the final call.

    Pass a shared `trace` list to watch events appear live, and a `usage` object to watch
    tokens grow live (every delegated run adds into the same usage).
    """
    deps = TeamDeps(ticket_id=ticket_id, stack=["boss"], trace=trace if trace is not None else [])
    deps.log("boss", "start", f"Ticket {ticket_id} received. Model: {MODEL_NAME}")
    async with mcp_toolset:
        result = await AGENTS["boss"].run(
            f"Resolve ticket {ticket_id}.", deps=deps, usage=usage,
            usage_limits=UsageLimits(request_limit=60))
    deps.log("boss", "reply", result.output.decision)
    return result.output, deps


def reset_database() -> None:
    """Restore the working copy from the untouched original. Run before every full run.

    The fresh copy (original + empty work tables) is built in memory, then written over the
    working DB with SQLite's backup API in one step, so nothing reads a half-reset database
    (and it works on Windows while other connections are open).
    """
    fresh = sqlite3.connect(":memory:")
    with closing(sqlite3.connect(ORIGINAL_DB)) as original:
        original.backup(fresh)
    fresh.executescript(WORK_TABLES_SQL)
    fresh.commit()
    with closing(sqlite3.connect(WORKING_DB)) as working:
        fresh.backup(working)
    fresh.close()


# ===================== API =====================

HUMAN = "Fran (human, dashboard)"
DEFAULT_RUN_SECONDS = 90  # estimate used until a run has finished

app = FastAPI(title="Campus Customs desk", version="1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENTS: list[TraceEvent] = []          # every event from every run, in order
TASKS: dict[int, asyncio.Task] = {}    # ticket_id -> running team task
RESULTS: dict[int, dict] = {}          # ticket_id -> Boss's final resolution
RUNS: dict[int, dict] = {}             # ticket_id -> timing, state and token usage of its latest run

STATE_FILE = HW5_DIR / "data" / "run_state.json"      # survives backend restarts; cleared on reset
AUDIT_FILE = HW5_DIR / "output" / "audit_trail.json"  # append-only record of real runs and human decisions


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


def save_state() -> None:
    runs = {tid: {k: v for k, v in r.items() if k != "usage"} | {
                "usage": {"requests": r["usage"].requests, "input_tokens": r["usage"].input_tokens,
                          "output_tokens": r["usage"].output_tokens}}
            for tid, r in RUNS.items()}
    STATE_FILE.write_text(json.dumps({"events": [e.model_dump(mode="json") for e in EVENTS],
                                      "results": RESULTS, "runs": runs}, indent=1), encoding="utf-8")


def load_state() -> None:
    if not STATE_FILE.exists():
        return
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    EVENTS.extend(TraceEvent(**e) for e in data["events"])
    RESULTS.update({int(k): v for k, v in data["results"].items()})
    for tid, r in data["runs"].items():
        if r["state"] == "running":  # the backend restarted mid-run
            r["state"], r["finished_at"] = "stopped", r["finished_at"] or time.time()
        RUNS[int(tid)] = r | {"usage": RunUsage(**r["usage"])}


def audit(entry: dict) -> None:
    """Append one entry to output/audit_trail.json (never rewrites past entries)."""
    trail = json.loads(AUDIT_FILE.read_text(encoding="utf-8")) if AUDIT_FILE.exists() else []
    trail.append({"recorded_at": datetime.now().isoformat(timespec="seconds"), **entry})
    AUDIT_FILE.write_text(json.dumps(trail, indent=1), encoding="utf-8")


async def autosave() -> None:
    while True:
        await asyncio.sleep(2)
        if any(not t.done() for t in TASKS.values()):
            save_state()


def db(path=WORKING_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


async def call_mcp(tool: str, args: dict | None = None) -> dict | list:
    """Call one MCP tool (this also makes the server create its work tables)."""
    async with mcp_client() as client:
        result = await client.call_tool(tool, args or {})
    return result.data if result.data is not None else json.loads(result.content[0].text)


async def ensure_work_tables() -> None:
    await call_mcp("list_open_tickets")


@app.on_event("startup")
async def startup() -> None:
    await ensure_work_tables()
    load_state()
    asyncio.create_task(autosave())


def add_event(**fields) -> None:
    EVENTS.append(TraceEvent(id=len(EVENTS) + 1, **fields))


def is_running(ticket_id: int) -> bool:
    return ticket_id in TASKS and not TASKS[ticket_id].done()


# ---------- runs: timing, tokens, estimated cost ----------

def cost_usd(usage: RunUsage) -> float:
    return round(usage.input_tokens / 1e6 * PRICE_INPUT_PER_1M + usage.output_tokens / 1e6 * PRICE_OUTPUT_PER_1M, 4)


def estimated_seconds() -> float:
    done = [r["finished_at"] - r["started_at"] for r in RUNS.values() if r["state"] == "finished"]
    return round(sum(done) / len(done)) if done else DEFAULT_RUN_SECONDS


def run_view(ticket_id: int) -> dict | None:
    r = RUNS.get(ticket_id)
    if r is None:
        return None
    u: RunUsage = r["usage"]
    end = r["finished_at"] or time.time()
    return {
        "state": r["state"],
        "elapsed_s": round(end - r["started_at"], 1),
        "estimated_total_s": estimated_seconds(),
        "requests": u.requests,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "total_tokens": u.input_tokens + u.output_tokens,
        "estimated_cost_usd": cost_usd(u),
    }


async def team_job(ticket_id: int) -> None:
    run = RUNS[ticket_id]
    try:
        # The run logs straight into EVENTS and adds tokens into run["usage"], so both update live.
        resolution, _ = await run_ticket(ticket_id, trace=EVENTS, usage=run["usage"])
        RESULTS[ticket_id] = resolution.model_dump()
        run["state"] = "finished"
        add_event(ticket_id=ticket_id, agent="boss", kind="done", text=resolution.decision)
    except asyncio.CancelledError:
        run["state"] = "stopped"
        add_event(ticket_id=ticket_id, agent="boss", kind="error", text="Run stopped by Fran.")
    except Exception as exc:
        run["state"] = "failed"
        add_event(ticket_id=ticket_id, agent="boss", kind="error", text=f"Run failed: {exc}")
    finally:
        run["finished_at"] = time.time()
        save_state()
        audit({"type": "agent_run", "ticket_id": ticket_id, "model": MODEL_NAME, "state": run["state"],
               "started_at": iso(run["started_at"]), "finished_at": iso(run["finished_at"]),
               "usage": run_view(ticket_id), "resolution": RESULTS.get(ticket_id),
               "events": [e.model_dump(mode="json") for e in EVENTS if e.ticket_id == ticket_id
                          and e.at.timestamp() >= run["started_at"] - 1]})


# ---------- tickets ----------

def pending_items(conn: sqlite3.Connection, ticket: sqlite3.Row) -> int:
    """Payments or purchase orders linked to this ticket that still wait on a human."""
    n = conn.execute("SELECT COUNT(*) FROM drafts WHERE kind = 'purchase_order' AND status = 'draft' AND ticket_id = ?",
                     (ticket["id"],)).fetchone()[0]
    if ticket["invoice_id"]:
        n += conn.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending' AND kind = 'invoice' AND ref_id = ?",
                          (ticket["invoice_id"],)).fetchone()[0]
    if ticket["lease_id"]:
        n += conn.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending' AND kind = 'rent' AND ref_id = ?",
                          (ticket["lease_id"],)).fetchone()[0]
    return n


def close_settled_tickets() -> None:
    """After a human decision: a finished ticket with nothing left waiting on Fran is closed."""
    with db() as conn:
        for t in conn.execute("SELECT * FROM tickets WHERE status != 'closed'").fetchall():
            if t["id"] in RESULTS and not is_running(t["id"]) and pending_items(conn, t) == 0:
                conn.execute("UPDATE tickets SET status = 'closed', notes = COALESCE(notes, '') || ? WHERE id = ?",
                             (f"\nClosed after human decision by {HUMAN}.", t["id"]))


@app.get("/")
def health() -> dict:
    return {"ok": True, "model": MODEL_NAME}


@app.get("/tickets")
def list_tickets() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["running"] = is_running(r["id"])
            r["waiting_on_human"] = pending_items(conn, row)
            run = RUNS.get(r["id"])
            if r["running"]:
                r["board_status"] = "running"
            elif run and run["state"] in ("stopped", "failed"):
                r["board_status"] = run["state"]
            elif r["status"] == "closed" or (r["id"] in RESULTS and not r["waiting_on_human"]):
                r["board_status"] = "resolved"
            elif r["id"] in RESULTS:
                r["board_status"] = "awaiting_approval"
            else:
                r["board_status"] = "open"
            r["resolution"] = RESULTS.get(r["id"])
            r["run"] = run_view(r["id"])
            out.append(r)
    return out


@app.post("/tickets/{ticket_id}/run")
async def run_team(ticket_id: int) -> dict:
    with db() as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            raise HTTPException(404, f"Ticket {ticket_id} not found.")
    if is_running(ticket_id):
        raise HTTPException(409, f"Ticket {ticket_id} is already running.")
    RESULTS.pop(ticket_id, None)
    RUNS[ticket_id] = {"state": "running", "started_at": time.time(), "finished_at": None, "usage": RunUsage()}
    TASKS[ticket_id] = asyncio.create_task(team_job(ticket_id))
    return {"ticket_id": ticket_id, "started": True, "model": MODEL_NAME,
            "estimated_total_s": estimated_seconds()}


@app.post("/tickets/{ticket_id}/stop")
async def stop_team(ticket_id: int) -> dict:
    if not is_running(ticket_id):
        raise HTTPException(409, f"Ticket {ticket_id} is not running.")
    TASKS[ticket_id].cancel()
    await asyncio.gather(TASKS[ticket_id], return_exceptions=True)
    return {"ticket_id": ticket_id, "stopped": True, "run": run_view(ticket_id)}


@app.get("/runs")
def runs() -> dict:
    """Token use and estimated cost per run. Accountability only, never charged to checking."""
    per_ticket = {tid: run_view(tid) for tid in RUNS}
    return {
        "model": MODEL_NAME,
        "price_per_1m_tokens": {"input": PRICE_INPUT_PER_1M, "output": PRICE_OUTPUT_PER_1M},
        "runs": per_ticket,
        "total_tokens": sum(r["total_tokens"] for r in per_ticket.values()),
        "total_estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in per_ticket.values()), 4),
        "note": "Estimate for accountability only. Not deducted from the checking balance.",
    }


@app.get("/events")
def events(since: int = 0, ticket_id: int | None = None, limit: int = 200) -> list[TraceEvent]:
    """Events after id `since` (what each agent said, delegated, and which tools it used)."""
    out = [e for e in EVENTS if e.id > since and (ticket_id is None or e.ticket_id == ticket_id)]
    return out[-limit:]


# ---------- human approvals ----------

@app.get("/approvals")
def list_approvals() -> dict:
    with db() as conn:
        approvals = [dict(r) for r in conn.execute("SELECT * FROM approvals ORDER BY id")]
        drafts = [dict(r) | {"payload": json.loads(r["payload"])}
                  for r in conn.execute("SELECT * FROM drafts ORDER BY id")]
    return {"payments": approvals, "drafts": drafts}


@app.post("/approvals/{approval_id}/approve")
async def approve_payment(approval_id: int) -> dict:
    """Human click: approve, then pay via the MCP execute_payment tool (refuses if funds are short)."""
    with db() as conn:
        ap = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if ap is None:
            raise HTTPException(404, f"Approval {approval_id} not found.")
        if ap["status"] != "pending":
            raise HTTPException(409, f"Approval {approval_id} is already '{ap['status']}'.")
        conn.execute("UPDATE approvals SET status = 'approved', decided_by = ? WHERE id = ?", (HUMAN, approval_id))
    result = await call_mcp("execute_payment", {"approval_id": approval_id})
    close_settled_tickets()
    audit({"type": "human_decision", "decision": "approve_payment", "approval_id": approval_id,
           "decided_by": HUMAN, "result": result, "checking_after": cash()["balance"]})
    return {"approval_id": approval_id, **result, "checking": cash()["balance"]}


@app.post("/approvals/{approval_id}/reject")
def reject_payment(approval_id: int) -> dict:
    with db() as conn:
        cur = conn.execute("UPDATE approvals SET status = 'rejected', decided_by = ? WHERE id = ? AND status = 'pending'",
                           (HUMAN, approval_id))
    if not cur.rowcount:
        raise HTTPException(409, f"Approval {approval_id} is not pending.")
    close_settled_tickets()
    audit({"type": "human_decision", "decision": "reject_payment", "approval_id": approval_id, "decided_by": HUMAN})
    return {"approval_id": approval_id, "status": "rejected", "paid": False}


@app.post("/drafts/{draft_id}/{decision}")
def decide_draft(draft_id: int, decision: str) -> dict:
    """Human decides a purchase order or message draft. Nothing is sent and no cash moves now.

    An approved purchase order becomes an account payable, so it is refused if checking
    minus what is already payable cannot cover it.
    """
    if decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be 'approve' or 'reject'.")
    with db() as conn:
        d = conn.execute("SELECT * FROM drafts WHERE id = ? AND status = 'draft'", (draft_id,)).fetchone()
    if d is None:
        raise HTTPException(409, f"Draft {draft_id} not found or already decided.")
    if decision == "approve" and d["kind"] == "purchase_order":
        cost = json.loads(d["payload"])["total_cost"]
        free = payables()["projected_balance"]
        if cost > free:
            raise HTTPException(409, f"PURCHASE REFUSED: INSUFFICIENT FUNDS. Costs ${cost:,.2f}, "
                                     f"only ${free:,.2f} is free after accounts payable.")
    status = "approved" if decision == "approve" else "rejected"
    with db() as conn:
        conn.execute("UPDATE drafts SET status = ?, decided_by = ? WHERE id = ?", (status, HUMAN, draft_id))
    close_settled_tickets()
    audit({"type": "human_decision", "decision": f"{decision}_{d['kind']}", "draft_id": draft_id,
           "ticket_id": d["ticket_id"], "decided_by": HUMAN, "payload": json.loads(d["payload"])})
    return {"draft_id": draft_id, "status": status, "sent": False}


# ---------- money ----------

@app.get("/cash")
def cash() -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM cash_accounts WHERE name = 'checking'").fetchone()
    return dict(row)


@app.get("/transactions")
def transactions() -> dict:
    """Checking history: starting balance from the original DB, then every payment with the running balance."""
    with db(ORIGINAL_DB) as conn:
        start = conn.execute("SELECT balance, date FROM cash_accounts WHERE name = 'checking'").fetchone()
    with db() as conn:
        pays = [dict(r) for r in conn.execute("SELECT * FROM payments WHERE account = 'checking' ORDER BY id")]
    balance, rows = start["balance"], []
    for p in pays:
        balance -= p["amount"]
        label = f"Invoice #{p['ref_id']}" if p["kind"] == "invoice" else f"Rent, lease #{p['ref_id']}"
        rows.append({"id": p["id"], "date": p["paid_at"], "label": label, "amount": -p["amount"],
                     "balance_after": round(balance, 2), "approved_by": p["approved_by"]})
    return {"starting_balance": start["balance"], "starting_date": start["date"], "transactions": rows,
            "current_balance": round(balance, 2)}


@app.get("/payables")
def payables() -> dict:
    """Approved purchase orders not yet paid in cash, due on delivery (vendor lead time)."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM drafts WHERE kind = 'purchase_order' AND status = 'approved' ORDER BY id")
        items = []
        for r in rows:
            p = json.loads(r["payload"])
            # Check blocking invoices live: the draft's snapshot goes stale once an invoice is paid.
            p["blocked_by_open_invoices"] = [i[0] for i in conn.execute(
                "SELECT id FROM invoices WHERE vendor_id = ? AND status != 'paid'", (p["vendor_id"],))]
            items.append({"draft_id": r["id"], "ticket_id": r["ticket_id"], "vendor": p["vendor"],
                          "description": f"{p['qty']}× {p['sku']} {p['size']}", "amount": p["total_cost"],
                          "due_date": p["earliest_arrival_if_sent_today"],
                          "blocked_by_open_invoices": p["blocked_by_open_invoices"]})
    total = round(sum(i["amount"] for i in items), 2)
    balance = cash()["balance"]
    return {"items": items, "total": total, "checking": balance, "projected_balance": round(balance - total, 2),
            "note": "Due on delivery (today + vendor lead days). Projection assumes no new money comes in."}


@app.post("/reset")
async def reset() -> dict:
    """Stops any running team, then restores the original database."""
    running = [t for t in TASKS.values() if not t.done()]
    for t in running:
        t.cancel()
    await asyncio.gather(*running, return_exceptions=True)
    reset_database()
    for store in (EVENTS, RESULTS, TASKS, RUNS):
        store.clear()
    STATE_FILE.unlink(missing_ok=True)
    audit({"type": "reset", "by": HUMAN, "note": "Working DB restored from the original campus_customs.db."})
    return {"reset": True, "stopped_runs": len(running), "checking": cash()["balance"],
            "tickets": [t["status"] for t in list_tickets()]}
