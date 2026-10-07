export const API = 'http://localhost:8000'

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export const AGENTS: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export interface Resolution {
  ticket_id: number
  decision: string
  rationale: string
  delegated_to: AgentName[]
  approval_ids: number[]
  draft_ids: number[]
  ticket_status: string
  next_steps: string[]
}

export interface RunInfo {
  state: 'running' | 'finished' | 'stopped' | 'failed'
  elapsed_s: number
  estimated_total_s: number
  requests: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  status: string
  notes: string | null
  board_status: 'open' | 'running' | 'awaiting_approval' | 'resolved' | 'stopped' | 'failed'
  running: boolean
  waiting_on_human: number
  resolution: Resolution | null
  run: RunInfo | null
}

export interface AgentEvent {
  id: number
  at: string
  ticket_id: number
  agent: AgentName
  kind: 'start' | 'delegate' | 'reply' | 'tool' | 'tool_result' | 'error' | 'done'
  target: AgentName | null
  tool: string | null
  text: string
}

export interface PaymentApproval {
  id: number
  kind: 'invoice' | 'rent'
  ref_id: number
  amount: number
  reason: string
  requested_by: string
  status: 'pending' | 'approved' | 'rejected' | 'paid' | 'refused'
  decided_by: string | null
  result: string | null
}

export interface Draft {
  id: number
  kind: 'purchase_order' | 'customer_message'
  ticket_id: number | null
  author: string
  status: 'draft' | 'approved' | 'rejected'
  payload: Record<string, unknown>
}

export interface Cash {
  name: string
  balance: number
  date: string
}

export interface Transactions {
  starting_balance: number
  starting_date: string
  current_balance: number
  transactions: { id: number; date: string; label: string; amount: number; balance_after: number; approved_by: string }[]
}

export interface Payables {
  items: { draft_id: number; ticket_id: number | null; vendor: string; description: string; amount: number; due_date: string; blocked_by_open_invoices: number[] }[]
  total: number
  checking: number
  projected_balance: number
  note: string
}

export interface Runs {
  model: string
  price_per_1m_tokens: { input: number; output: number }
  total_tokens: number
  total_estimated_cost_usd: number
  note: string
}

async function call<T>(path: string, method = 'GET'): Promise<T> {
  const res = await fetch(API + path, { method })
  const body = await res.json()
  if (!res.ok) throw new Error(body.detail ?? res.statusText)
  return body as T
}

export const api = {
  tickets: () => call<Ticket[]>('/tickets'),
  run: (id: number) => call<{ started: boolean; estimated_total_s: number }>(`/tickets/${id}/run`, 'POST'),
  stop: (id: number) => call(`/tickets/${id}/stop`, 'POST'),
  runs: () => call<Runs>('/runs'),
  transactions: () => call<Transactions>('/transactions'),
  payables: () => call<Payables>('/payables'),
  events: (since: number) => call<AgentEvent[]>(`/events?since=${since}&limit=1000`),
  approvals: () => call<{ payments: PaymentApproval[]; drafts: Draft[] }>('/approvals'),
  approvePayment: (id: number) => call<{ paid?: boolean; refused?: boolean; reason?: string }>(`/approvals/${id}/approve`, 'POST'),
  rejectPayment: (id: number) => call(`/approvals/${id}/reject`, 'POST'),
  decideDraft: (id: number, decision: 'approve' | 'reject') => call(`/drafts/${id}/${decision}`, 'POST'),
  cash: () => call<Cash>('/cash'),
  reset: () => call('/reset', 'POST'),
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
