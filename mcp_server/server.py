"""Campus Customs MCP server.

All tools read/write the working copy data/campus_customs_new.db.
To add a tool: write a function below and decorate it with @mcp.tool.
"""

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def today(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def add_one_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, 28)).isoformat()


# Agent work tables (human-approval queue and drafts). Created only in the working copy.
# backend/main.py keeps the same definition for database resets.
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


def ensure_work_tables() -> None:
    with connect() as conn:
        conn.executescript(WORK_TABLES_SQL)


@mcp.tool
def check_stock(sku: str, size: str) -> dict:
    """Stock on hand for one SKU and size, plus its unit cost, list price and margin."""
    with connect() as conn:
        row = conn.execute(
            """SELECT i.sku, i.name, i.size, i.qty, i.location,
                      p.unit_cost, p.list_price
               FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku
               WHERE i.sku = ? AND i.size = ?""",
            (sku, size),
        ).fetchone()
    if row is None:
        return {"error": f"No inventory row for sku={sku} size={size}."}
    result = dict(row)
    if row["unit_cost"] is not None:
        result["unit_margin"] = round(row["list_price"] - row["unit_cost"], 2)
    return result


@mcp.tool
def get_invoice_status(invoice_id: int) -> dict:
    """Vendor invoice with its vendor, lead time, and days overdue versus desk.date_today.

    An open invoice blocks that vendor from delivering anything new.
    """
    with connect() as conn:
        row = conn.execute(
            """SELECT inv.id, inv.amount, inv.due_date, inv.status, inv.description,
                      v.id AS vendor_id, v.name AS vendor_name, v.lead_days
               FROM invoices inv JOIN vendors v ON v.id = inv.vendor_id
               WHERE inv.id = ?""",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {"error": f"Invoice {invoice_id} not found."}
        now = today(conn)
    result = dict(row)
    result["today"] = now
    result["days_overdue"] = max(0, days_between(row["due_date"], now))
    result["blocks_vendor_delivery"] = row["status"] != "paid"
    return result


@mcp.tool
def get_lease_and_cash(lease_id: int) -> dict:
    """Lease rent and due date, days until due, and the current cash balance."""
    with connect() as conn:
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if lease is None:
            return {"error": f"Lease {lease_id} not found."}
        cash = [dict(r) for r in conn.execute("SELECT * FROM cash_accounts")]
        now = today(conn)
    result = dict(lease)
    result["today"] = now
    result["days_until_due"] = days_between(now, lease["next_due"])
    result["cash_accounts"] = cash
    return result


@mcp.tool
def get_cash_balance() -> dict:
    """Current balance of every cash account and desk.date_today. The shop has no incoming money."""
    with connect() as conn:
        return {"today": today(conn), "cash_accounts": [dict(r) for r in conn.execute("SELECT * FROM cash_accounts")]}


@mcp.tool
def list_open_tickets() -> list[dict]:
    """All tickets that are not closed, oldest first."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM tickets WHERE status != 'closed' ORDER BY created_at")]


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """One ticket with its linked sku/size, lease and invoice ids."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else {"error": f"Ticket {ticket_id} not found."}


@mcp.tool
def list_vendors() -> list[dict]:
    """Vendors with specialty, lead time, and whether an open invoice blocks new deliveries."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT v.*, COUNT(i.id) AS open_invoices, COALESCE(SUM(i.amount), 0) AS open_amount
               FROM vendors v LEFT JOIN invoices i ON i.vendor_id = v.id AND i.status != 'paid'
               GROUP BY v.id""").fetchall()
    return [dict(r) | {"blocked": r["open_invoices"] > 0} for r in rows]


@mcp.tool
def list_payments_and_approvals(kind: str | None = None, ref_id: int | None = None) -> dict:
    """Payments already made and payment approval requests, optionally filtered by kind and ref_id.

    Check this before requesting a payment so nothing is ever paid twice.
    """
    where, args = [], []
    if kind:
        where.append("kind = ?")
        args.append(kind)
    if ref_id is not None:
        where.append("ref_id = ?")
        args.append(ref_id)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn:
        return {
            "payments": [dict(r) for r in conn.execute(f"SELECT * FROM payments{clause}", args)],
            "approvals": [dict(r) for r in conn.execute(f"SELECT * FROM approvals{clause}", args)],
        }


def amount_owed(conn: sqlite3.Connection, kind: str, ref_id: int) -> dict:
    """Amount owed for an invoice or lease from the DB, or an error if it is not payable."""
    if kind == "invoice":
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
        if inv is None:
            return {"error": f"Invoice {ref_id} not found."}
        if inv["status"] == "paid":
            return {"error": f"Invoice {ref_id} is already paid. Never pay twice."}
        return {"amount": inv["amount"]}
    if kind == "rent":
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
        if lease is None:
            return {"error": f"Lease {ref_id} not found."}
        return {"amount": lease["monthly_rent"]}
    return {"error": "kind must be 'invoice' or 'rent'."}


@mcp.tool
def request_payment_approval(kind: str, ref_id: int, reason: str, requested_by: str) -> dict:
    """Queue a payment ('invoice' or 'rent') for HUMAN approval. No money moves here.

    The amount always comes from the database, never from the agent.
    """
    with connect() as conn:
        owed = amount_owed(conn, kind, ref_id)
        if "error" in owed:
            return owed
        dup = conn.execute(
            "SELECT id, status FROM approvals WHERE kind = ? AND ref_id = ? AND status IN ('pending', 'approved')",
            (kind, ref_id)).fetchone()
        if dup:
            return {"error": f"Approval {dup['id']} for this {kind} already exists ({dup['status']})."}
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
        cur = conn.execute(
            "INSERT INTO approvals (kind, ref_id, amount, reason, requested_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, owed["amount"], reason, requested_by, today(conn)))
    return {"approval_id": cur.lastrowid, "status": "pending", "kind": kind, "ref_id": ref_id,
            "amount": owed["amount"], "cash_now": cash, "funds_sufficient_now": cash >= owed["amount"],
            "note": "Waiting for human approval. Nothing has been paid."}


@mcp.tool
def execute_payment(approval_id: int) -> dict:
    """Pay an approval a HUMAN already approved. Refuses if not approved or if cash is insufficient."""
    with connect() as conn:
        ap = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if ap is None:
            return {"error": f"Approval {approval_id} not found."}
        if ap["status"] != "approved" or not ap["decided_by"]:
            return {"refused": True, "reason": f"Approval {approval_id} is '{ap['status']}'. "
                    "A human must approve it first. No payment was made."}
        owed = amount_owed(conn, ap["kind"], ap["ref_id"])
        if "error" in owed:
            conn.execute("UPDATE approvals SET status = 'refused', result = ? WHERE id = ?", (owed["error"], approval_id))
            return {"refused": True, "reason": owed["error"]}
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
        if cash < ap["amount"]:
            msg = (f"PAYMENT REFUSED: INSUFFICIENT FUNDS. Needs ${ap['amount']:,.2f}, checking has "
                   f"${cash:,.2f}. Cash can never go negative. No payment was made.")
            conn.execute("UPDATE approvals SET status = 'refused', result = ? WHERE id = ?", (msg, approval_id))
            return {"refused": True, "reason": msg}
        now = today(conn)
        conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = 'checking'",
                     (ap["amount"], now))
        conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (ap["kind"], ap["ref_id"], ap["amount"], "checking", now, ap["decided_by"]))
        if ap["kind"] == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ap["ref_id"],))
        else:
            due = conn.execute("SELECT next_due FROM leases WHERE id = ?", (ap["ref_id"],)).fetchone()[0]
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (add_one_month(due), ap["ref_id"]))
        conn.execute("UPDATE approvals SET status = 'paid', result = 'paid' WHERE id = ?", (approval_id,))
    return {"paid": True, "approval_id": approval_id, "amount": ap["amount"],
            "cash_after": round(cash - ap["amount"], 2)}


@mcp.tool
def draft_purchase_order(vendor_id: int, sku: str, size: str, qty: int, author: str,
                         ticket_id: int | None = None, notes: str = "") -> dict:
    """Draft (never send) a restock purchase order, costed, with arrival estimated from vendor lead time."""
    with connect() as conn:
        v = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if v is None or p is None:
            return {"error": "Unknown vendor or sku."}
        dup = conn.execute(
            """SELECT id FROM drafts WHERE kind = 'purchase_order' AND status = 'draft'
               AND json_extract(payload, '$.vendor_id') = ? AND json_extract(payload, '$.sku') = ?
               AND json_extract(payload, '$.size') = ? AND COALESCE(ticket_id, -1) = COALESCE(?, -1)""",
            (vendor_id, sku, size, ticket_id)).fetchone()
        if dup:
            return {"error": f"Purchase order draft {dup['id']} already exists for this item. Do not draft it twice."}
        blocking = [r["id"] for r in conn.execute(
            "SELECT id FROM invoices WHERE vendor_id = ? AND status != 'paid'", (vendor_id,))]
        now = today(conn)
        payload = {"vendor": v["name"], "vendor_id": vendor_id, "sku": sku, "size": size, "qty": qty,
                   "unit_cost": p["unit_cost"], "total_cost": round(p["unit_cost"] * qty, 2),
                   "lead_days": v["lead_days"],
                   "earliest_arrival_if_sent_today": (date.fromisoformat(now) + timedelta(days=v["lead_days"])).isoformat(),
                   "blocked_by_open_invoices": blocking, "notes": notes}
        cur = conn.execute("INSERT INTO drafts (kind, ticket_id, author, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                           ("purchase_order", ticket_id, author, json.dumps(payload), now))
    return {"draft_id": cur.lastrowid, "status": "draft (not sent)", **payload}


@mcp.tool
def draft_customer_message(ticket_id: int, to: str, subject: str, body: str, author: str) -> dict:
    """Draft (never send) a message to a customer or landlord for human review."""
    payload = {"to": to, "subject": subject, "body": body}
    with connect() as conn:
        cur = conn.execute("INSERT INTO drafts (kind, ticket_id, author, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                           ("customer_message", ticket_id, author, json.dumps(payload), today(conn)))
    return {"draft_id": cur.lastrowid, "status": "draft (not sent)", **payload}


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str) -> dict:
    """Set a ticket status ('open', 'in_progress', 'waiting_approval', 'closed') and append a note."""
    if status not in {"open", "in_progress", "waiting_approval", "closed"}:
        return {"error": "Invalid status."}
    with connect() as conn:
        cur = conn.execute("UPDATE tickets SET status = ?, notes = COALESCE(notes, '') || ? WHERE id = ?",
                           (status, f"\n[{today(conn)}] {note}", ticket_id))
    return {"ticket_id": ticket_id, "status": status} if cur.rowcount else {"error": "Ticket not found."}


ensure_work_tables()

if __name__ == "__main__":
    mcp.run()
