# Campus Customs MCP Server

**Purpose:** one shared toolbox (FastMCP) that every Campus Customs agent (Boss, Inventory, Accounting, Facilities, Customer Service) uses to read and update the shop database. New tools are added in `server.py` with `@mcp.tool`.

**Database:** `data/campus_customs_new.db` (working copy). The original `data/campus_customs.db` is never touched; it is kept for audit and resets.

**Run:** `python mcp_server/server.py`

## Tools

| Tool | What it returns |
|---|---|
| `check_stock(sku, size)` | Qty on hand and location for one SKU and size, with unit cost, list price and unit margin. |
| `get_invoice_status(invoice_id)` | Invoice amount, status and due date, the vendor and its lead days, days overdue, and whether it blocks delivery. |
| `get_lease_and_cash(lease_id)` | Rent, due date and days until due, plus the current cash balance. |
| `list_open_tickets()` | All tickets not closed, oldest first. |
| `get_ticket(ticket_id)` | One ticket with its linked sku/size, lease and invoice. |
| `list_vendors()` | Vendors with lead days and whether an open invoice blocks them. |
| `list_payments_and_approvals(kind?, ref_id?)` | Payments made and approval requests, so nothing is paid twice. |
| `request_payment_approval(kind, ref_id, reason, requested_by)` | Queues an invoice/rent payment for human approval; amount comes from the DB. No money moves. |
| `execute_payment(approval_id)` | Pays only a human-approved request; refuses on insufficient funds. Not given to any agent. |
| `draft_purchase_order(...)` | Costed restock draft with earliest arrival; never sent. |
| `draft_customer_message(...)` | Message draft for human review; never sent. |
| `update_ticket(ticket_id, status, note)` | Sets ticket status and appends a note. |

Work tables `approvals` and `drafts` are created in the working copy on startup.
