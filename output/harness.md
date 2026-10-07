# Campus Customs — Agent Harness

Working DB: `data/campus_customs_new.db` (copy). Original `data/campus_customs.db` is never written; it is the audit and reset source.

## Problem 2 — Database tables

| Table | Fields | Why the agent needs it |
|---|---|---|
| `desk` | date_today, notes | The shop's "today" (2026-08-31); every overdue/due-soon check uses it, not the real clock. |
| `inventory` | sku, name, size, qty, location (PK sku+size) | Inventory agent checks stock per SKU **and size** to spot shortfalls. |
| `pricing` | sku, unit_cost, list_price | Accounting checks margins before any discount and costs restocks. |
| `vendors` | id, name, specialty, lead_days | Inventory picks the right restock vendor; lead_days tells how late stock arrives. |
| `leases` | id, space_name, landlord, monthly_rent, next_due, notes | Facilities tracks rent owed and its due date. |
| `cash_accounts` | name, balance, date | Single source of available cash; payments can never push it below zero. |
| `payments` | id, kind, ref_id, amount, account, paid_at, approved_by | Audit log of approved payments; checking it prevents paying twice. |
| `invoices` | id, vendor_id, amount, due_date, status, description | Vendor bills; an unpaid invoice blocks that vendor's next delivery. |
| `tickets` | id, type, requester, subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at | The Boss's work queue; each ticket links to the stock, lease or invoice it concerns. |

## Open tickets (2026-08-31)

| # | Type | Requester | Request | Linked data | Key issue |
|---|---|---|---|---|---|
| 101 | customer_order | Tauhid Zaman | 1× CC-TEE-WHITE, S | invoice 501 ($840, Bulldog Print Co) | S stock = 0; invoice overdue since 08-28 and still open, so no reprint delivery until paid (+5 lead days). |
| 102 | rent_notice | Elm City Properties | Rent due | lease 1 ($2,400, due 09-02) | Due in 2 days. |
| 103 | price_override | Yale AI Club | 20× CC-HOOD-NAVY, M, bulk discount | — | Only 8 M in stock (short 12); margin at list $58 vs cost $22 limits the discount. |

Cash check: $3,400 − $840 − $2,400 = **$160** left; restocking 12 hoodies costs $264, so it can't all be paid.

## Problem 3 — MCP server tools (`mcp_server/server.py`, FastMCP)

| Tool | Reads tables | Ticket | Why it's the most useful tool for that ticket |
|---|---|---|---|
| `check_stock(sku, size)` | inventory, pricing | 103 (also 101) | Shows only 8 of 20 M hoodies on hand and the $36 unit margin that bounds any bulk discount. |
| `get_invoice_status(invoice_id)` | invoices, vendors, desk | 101 | Shows invoice 501 is 3 days overdue and blocks Bulldog Print's S-tee reprint (5-day lead time). |
| `get_lease_and_cash(lease_id)` | leases, cash_accounts, desk | 102 | Shows $2,400 rent due in 2 days against the $3,400 cash balance. |

## Problem 4 — Connected to the vibe coder

Registered in the project-root `.mcp.json` as `campus-customs` (`python hw5/mcp_server/server.py`, stdio). All 3 tools were tested over stdio and returned live DB values; an unknown SKU returns a clear error instead of invented data.

## Problem 5 — Agent team (PydanticAI) and new MCP tools

**Model: `gpt-6-luna` for all 5 agents** (Portkey → OpenAI Responses API; the API answers as `gpt-6-luna-global`). Set once in `backend/main.py` (`MODEL_NAME`).

| Agent | Persona (Fran's touch) | MCP tools |
|---|---|---|
| boss | Shares work as evenly as possible (`team_workload`); quality over speed | get_ticket, list_open_tickets, update_ticket |
| inventory | Very detail-oriented, hands-on | get_ticket, check_stock, list_vendors, get_invoice_status, draft_purchase_order |
| accounting | Very ethical: never pays, never double-pays, never hides shortfalls | get_ticket, check_stock, get_invoice_status, get_lease_and_cash, list_vendors, list_payments_and_approvals, request_payment_approval |
| facilities | Great at multitasking | get_ticket, get_lease_and_cash |
| customer_service | Sensitive to very different audiences | get_ticket, draft_customer_message |

**Fully connected:** every agent has `ask_teammate(teammate, task)`; any agent can delegate to any other (no self-delegation, max depth 3). Each step is logged as a `TraceEvent` for the dashboard.

**New MCP tools:** `list_open_tickets`, `get_ticket`, `list_vendors`, `list_payments_and_approvals`, `request_payment_approval` (queues; amount read from DB), `execute_payment` (**no agent has it**; only runs on a human-approved request; refuses with "PAYMENT REFUSED: INSUFFICIENT FUNDS" if cash would go negative; updates invoices/leases, payments, cash), `draft_purchase_order`, `draft_customer_message` (drafts only, never sent), `update_ticket`. New work tables in the copy only: `approvals`, `drafts`.

**Smoke test (read-only):** facilities → accounting on ticket 102: rent $2,400 due in 2 days; $3,400 cash covers rent + invoice 501 ($840), leaving $160. No DB writes.

## Problem 6 — Ticket plan (`output/desk_tickets.html`)

| Ticket | Boss calls first | Specialists (only those needed) |
|---|---|---|
| 101 | Inventory (S stock = 0; restock blocked by invoice 501) | inventory → accounting, customer_service |
| 102 | Facilities (owns lease; rent due in 2 days) | facilities → accounting |
| 103 | Inventory (8 of 20 M on hand) | inventory, accounting, customer_service |

Total: 8 specialist calls across 3 tickets instead of 12; Facilities only on 102.

## Problem 7 — Backend routes (`backend/main.py`, FastAPI)

Start from `backend/`: `uvicorn main:app --reload --port 8000` → http://localhost:8000 (CORS open to the Vite dashboard on :5173). Model: **gpt-6-luna**.

- `GET  /` — health check; returns the model in use (`gpt-6-luna`).
- `GET  /tickets` — all tickets with DB status, board status (open/resolved), whether the team is running, and the Boss's final resolution.
- `POST /tickets/{id}/run` — starts the agent team on that ticket in the background (409 if already running).
- `GET  /events?since=N&ticket_id=T` — recent agent events in order: delegations, replies, every MCP tool call and its result.
- `GET  /approvals` — payment approvals waiting/decided, plus purchase-order and message drafts.
- `POST /approvals/{id}/approve` — the human click: marks it approved, then pays via MCP `execute_payment` (only route that changes cash; refuses with "PAYMENT REFUSED: INSUFFICIENT FUNDS").
- `POST /approvals/{id}/reject` — human rejects a payment; nothing is paid.
- `POST /drafts/{id}/approve` · `POST /drafts/{id}/reject` — human decides a purchase order or message draft; nothing is sent and no cash moves (vendor bills later).
- `GET  /cash` — current checking balance from `cash_accounts`.
- `POST /reset` — copies the original `campus_customs.db` over the working copy and clears events/results.

Route test: approve 501 → $2,560; approve rent → $160; second approve of the same id → 409; a $2,400 request with $160 → refused for insufficient funds; reset → $3,400.

## Problem 8 — Dashboard (`frontend/`, React + Vite + TypeScript)

`npm run dev` in `frontend/` → http://localhost:5173 (opens the browser), polling the backend at http://localhost:8000 every 1.5 s. Sections: checking balance (top right), ticket menu + ▶ Play + reset, 3 ticket cards with a ✔ Resolved flag when the run finishes, "Agents live" (one short line per agent), per-agent summary for the selected ticket, human approvals (payments, purchase orders, message drafts; Approve is disabled with "NOT ENOUGH CASH" when the amount exceeds checking), activity feed.

Test: Play #102 → Boss → Facilities → Accounting (matches the Problem 6 plan), rent queued; Approve & pay → balance $3,400 → $1,000; a $2,400 request with $1,000 → "NOT ENOUGH CASH", button disabled. DB reset afterward.

### Problem 8 — Changes requested by Fran
- Toasts are honest: "Run #N started · the team is working" on Play; "finished/stopped in m:ss · tokens · cost" only when it actually ends.
- Live run meter per ticket: elapsed time, progress bar and ≈time left (estimate = average of finished runs, 90 s default), then "Took m:ss".
- Tokens + estimated AI cost per run and per session (`GET /runs`), priced at ASSUMED gpt-6-luna rates in `backend/main.py` ($1.25/1M input, $10/1M output). Accountability only, never deducted from checking.
- Flags: Working / Waiting for Fran / ✔ Resolved / Stopped. A ticket closes in the DB once Fran decides everything linked to it (fixes "resolved but waiting_approval"). DB status removed from cards.
- Yale-inspired blue-and-white look (Yale Blue #00356b masthead, serif headings, white cards).
- Blocking approval banners, one stacked layer per pending payment or purchase: Approve / Decline / Close. When cash can't cover it, Approve is disabled, Close is hidden and only Decline is allowed. Stop and Reset stay reachable on the overlay.
- "Checking transactions" menu above the balance (`GET /transactions`): starting $3,400, then each payment with the running balance.
- Accounts payable (`GET /payables`): approved purchase orders, not paid now, due on delivery (today + vendor lead days); projected savings = checking − payables. Approving a PO is refused if it exceeds that.
- New routes: `POST /tickets/{id}/stop` (stop a ticket), `GET /runs`, `GET /transactions`, `GET /payables`; `POST /reset` now stops runs first and swaps in a fully built copy.
- Agent fixes after a looping run (5:37, 92k tokens): new MCP tool `get_cash_balance`; duplicate PO drafts refused; specialists can't send work back to the Boss; 8-delegation budget per run; Customer Service addresses drafts to the requester's name. Re-run of #101: 53 s, 25.6k tokens, ≈$0.06, exactly the Problem 6 plan.

## Problem 9 — Real runs and final harness coverage

### Results (real runs on gpt-6-luna, after a fresh reset)
| Ticket | Agents (in order) | Time · tokens · ≈AI cost | Human decision (Fran) | Final status |
|---|---|---|---|---|
| 101 | Boss → Inventory → Accounting; Boss → Customer Service | 56 s · 26,935 · $0.06 | Paid invoice 501 ($840); approved 1-tee PO ($8, payable 09-05); approved Tauhid draft | closed |
| 102 | Boss → Facilities → Accounting | 27 s · 13,858 · $0.03 | Rent $2,400 left pending | waiting_approval |
| 103 | Boss → Accounting ⇄ Inventory; Boss → Inventory → Accounting; Boss → Customer Service; Boss → Accounting | 128 s · 54,905 · $0.14 | 12-hoodie PO ($264) and Yale AI Club draft left pending | waiting_approval |

Checking: $3,400 → **$2,560** (only invoice 501 paid), matching `cash_accounts`. Outputs: `resolved_tickets.json`, `desk_tickets.html` (Actual + Cash tabs), `resolved_board.html` (3 embedded screenshots), `audit_trail.json`.
Plan vs actual: 101 and 102 matched the Problem 6 plan exactly. 103 used the planned 3 specialists but Boss called Accounting before Inventory, and Accounting/Inventory traded one question back and forth (only sending work back to the Boss is blocked today).
Note: Portkey had cached an earlier identical run (7 s, same tokens). Requests now send `x-portkey-cache-force-refresh: true`, so every recorded run is a fresh model answer.

### Coverage checklist
**Tables** — original 9 (`desk`, `inventory`, `pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, `invoices`, `tickets`, see Problem 2) plus 2 work tables in the copy only, defined in `mcp_server/server.py` (mirrored in `backend/main.py` for resets): `approvals` (payment requests: pending → approved/rejected → paid/refused, with `decided_by`) and `drafts` (purchase orders and messages: draft → approved/rejected). Backend state survives restarts in `data/run_state.json` (cleared on reset).

**MCP tools (13, `mcp_server/server.py`)** — read: `check_stock`, `get_invoice_status`, `get_lease_and_cash`, `get_cash_balance`, `list_open_tickets`, `get_ticket`, `list_vendors`, `list_payments_and_approvals`. Write (safe): `request_payment_approval`, `draft_purchase_order`, `draft_customer_message`, `update_ticket`. Money: `execute_payment` (backend only, after a human approval).

**5 agents (`backend/main.py`, prompts in `backend/prompts/`, types in `backend/models.py`)** — all gpt-6-luna via Portkey (OpenAI Responses API). Boss (fair share of work, quality over speed), Inventory (detail-oriented, hands-on), Accounting (ethical), Facilities (multitasker), Customer Service (sensitive to every audience). Fully connected through `ask_teammate`; each has only the MCP tools its role needs.

**API routes (`backend/main.py`)** — `GET /`, `GET /tickets`, `POST /tickets/{id}/run`, `POST /tickets/{id}/stop`, `GET /events`, `GET /runs`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`, `POST /drafts/{id}/approve|reject`, `GET /cash`, `GET /transactions`, `GET /payables`, `POST /reset`.

**Dashboard (`frontend/`, React + Vite + TS, `npm run dev`)** — tickets with live meter and flags, Play / Stop ticket / Reset database, agents live, per-ticket summary, blocking stacked approval banners, accounts payable, checking transactions menu, AI token/cost line, activity feed.

**Safety rules (and where they are enforced)**
- Today = `desk.date_today`: every date tool reads it; prompts forbid the real clock.
- Unpaid invoice blocks a vendor: `get_invoice_status`, `list_vendors` and `draft_purchase_order` flag it.
- No payment without a human: no agent has `execute_payment`; it refuses unless `approvals.status='approved'` with `decided_by`; only `POST /approvals/{id}/approve` (Fran's click) sets that.
- Never negative cash: `execute_payment` refuses with "PAYMENT REFUSED: INSUFFICIENT FUNDS"; banners disable Approve; PO approval refused beyond checking − payables.
- No double charging: amounts come from the DB; already-paid invoices and duplicate approvals/PO drafts are refused.
- Money only goes out: projections assume no inflows.
- Reset before a full run: `POST /reset` stops runs and restores `campus_customs.db` via SQLite backup; the original is never written.
- Drafts only: messages and POs are never sent; approving a draft sets `sent: false`.
- Loops bounded: max depth 3, 8 delegations per run, 60 model requests, no sending work back to the Boss.
- Accountability: every run, human decision and reset is appended to `output/audit_trail.json`; AI cost is never charged to checking.

## Problem 11 — Repository layout
Published layout matches Fran's tree exactly: settings and the agent team were folded into `backend/main.py` (with `models.py` and `prompts/`), and the work-table schema lives in `mcp_server/server.py`. Not published: `.env` (placeholder `.env.example` instead), every database under `data/` (only `data/.gitkeep`), `data/run_state.json`, `node_modules/`.
