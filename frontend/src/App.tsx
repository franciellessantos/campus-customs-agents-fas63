import { useCallback, useEffect, useRef, useState } from 'react'
import type React from 'react'
import { AGENTS, api, clock, money } from './api'
import type { AgentEvent, AgentName, Cash, Draft, Payables, PaymentApproval, Runs, Ticket, Transactions } from './api'

const LABEL: Record<AgentName, string> = {
  boss: 'Boss',
  inventory: 'Inventory',
  accounting: 'Accounting',
  facilities: 'Facilities',
  customer_service: 'Customer Service',
}

const FLAG: Record<Ticket['board_status'], string> = {
  open: 'Open',
  running: '● Working',
  awaiting_approval: '⏳ Waiting for Fran',
  resolved: '✔ Resolved',
  stopped: '■ Stopped',
  failed: '✖ Failed',
}

const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

/** One short line describing an event. */
function shortLine(e: AgentEvent): string {
  switch (e.kind) {
    case 'start': return `#${e.ticket_id} started`
    case 'delegate': return `→ asks ${LABEL[e.target!]}: ${cut(e.text, 70)}`
    case 'tool': return `uses ${e.tool}`
    case 'tool_result': return `got ${e.tool} result`
    case 'reply': return `says: ${cut(e.text, 90)}`
    case 'done': return `final call: ${cut(e.text, 90)}`
    case 'error': return cut(e.text, 90)
  }
}

export type Act = (label: string, fn: () => Promise<unknown>) => Promise<void>

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [payments, setPayments] = useState<PaymentApproval[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [tx, setTx] = useState<Transactions | null>(null)
  const [payables, setPayables] = useState<Payables | null>(null)
  const [runs, setRuns] = useState<Runs | null>(null)
  const [selected, setSelected] = useState<number>(101)
  const [message, setMessage] = useState<string>('')
  const [offline, setOffline] = useState(false)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const lastId = useRef(0)
  const prevStatus = useRef<Record<number, string>>({})

  const refresh = useCallback(async () => {
    try {
      const [t, ev, ap, c, txs, pay, r] = await Promise.all([
        api.tickets(), api.events(lastId.current), api.approvals(), api.cash(),
        api.transactions(), api.payables(), api.runs(),
      ])
      // Announce when a run ends (never before).
      for (const tk of t) {
        if (prevStatus.current[tk.id] === 'running' && tk.board_status !== 'running' && tk.run) {
          const how = tk.run.state === 'finished' ? 'finished' : tk.run.state
          setMessage(`Run #${tk.id} ${how} in ${clock(tk.run.elapsed_s)} · ${tk.run.total_tokens.toLocaleString()} tokens · ≈${money(tk.run.estimated_cost_usd)}`)
        }
        prevStatus.current[tk.id] = tk.board_status
      }
      setTickets(t)
      if (ev.length) {
        lastId.current = Math.max(lastId.current, ev[ev.length - 1].id)
        // Overlapping polls can return the same events; keep each id once.
        setEvents(prev => {
          const seen = new Set(prev.map(e => e.id))
          return [...prev, ...ev.filter(e => !seen.has(e.id))]
        })
      }
      setPayments(ap.payments)
      setDrafts(ap.drafts)
      setCash(c)
      setTx(txs)
      setPayables(pay)
      setRuns(r)
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 1000)
    return () => clearInterval(timer)
  }, [refresh])

  const act: Act = async (label, fn) => {
    try {
      const r = await fn() as { refused?: boolean; reason?: string } | undefined
      setMessage(r?.refused ? `Refused: ${r.reason}` : label)
    } catch (err) {
      setMessage(`${label.split(' ·')[0]} failed: ${(err as Error).message}`)
    }
    refresh()
  }

  const reset = () => {
    if (!confirm('Stop every run and reset the database to the original?')) return
    act('Database reset to the original. Checking is back to the starting balance.', async () => {
      await api.reset()
      lastId.current = 0
      prevStatus.current = {}
      setEvents([])
      setDismissed(new Set())
    })
  }

  const running = tickets.filter(t => t.running).map(t => t.id)
  const current = tickets.find(t => t.id === selected)
  const ticketEvents = events.filter(e => e.ticket_id === selected)
  const balance = cash?.balance ?? 0

  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <div>
            <div className="eyebrow">Campus Customs</div>
            <h1>Operations Desk</h1>
          </div>
          <div className="money">
            <details className="tx">
              <summary>Checking transactions</summary>
              {tx && (
                <table>
                  <tbody>
                    <tr><td>{tx.starting_date}</td><td>Starting balance</td><td className="num">{money(tx.starting_balance)}</td></tr>
                    {tx.transactions.map(t => (
                      <tr key={t.id}><td>{t.date}</td><td>{t.label}</td><td className="num neg">{money(t.amount)}<div className="small">bal. {money(t.balance_after)}</div></td></tr>
                    ))}
                    {tx.transactions.length === 0 && <tr><td colSpan={3} className="small">No payments yet.</td></tr>}
                  </tbody>
                </table>
              )}
            </details>
            <div className="cash" aria-live="polite">
              <span>Checking balance</span>
              <strong>{cash ? money(balance) : '…'}</strong>
            </div>
          </div>
        </div>
      </header>

      <main className="page">
        {offline && <p className="notice bad" role="alert">Can't reach the backend at http://localhost:8000.</p>}
        {message && <p className="notice" role="status">{message} <button className="link" onClick={() => setMessage('')}>dismiss</button></p>}

        {/* Tickets + controls */}
        <section className="card">
          <h2>Tickets</h2>
          <div className="controls">
            <label>
              Ticket{' '}
              <select value={selected} onChange={e => setSelected(Number(e.target.value))}>
                {tickets.map(t => <option key={t.id} value={t.id}>#{t.id} · {t.subject}</option>)}
              </select>
            </label>
            <button className="primary" disabled={!current || current.running}
                    onClick={() => act(`Run #${selected} started · the team is working on it now.`, () => api.run(selected))}>
              ▶ Play
            </button>
            <button className="secondary" disabled={!current?.running}
                    onClick={() => act(`Run #${selected} stopped.`, () => api.stop(selected))}>
              ■ Stop ticket
            </button>
            <button className="danger" onClick={reset}>Reset database</button>
          </div>
          <div className="tickets">
            {tickets.map(t => (
              <button key={t.id} className={`ticket ${t.id === selected ? 'selected' : ''}`} onClick={() => setSelected(t.id)}>
                <div className="row">
                  <strong>#{t.id}</strong>
                  <span className={`flag ${t.board_status}`}>{FLAG[t.board_status]}</span>
                </div>
                <div className="subject">{t.subject}</div>
                <div className="small muted">{t.requester}{t.sku ? ` · ${t.qty}× ${t.sku} ${t.size}` : ''}</div>
                {t.run && <RunMeter run={t.run} />}
              </button>
            ))}
          </div>
          {runs && (
            <p className="small muted usage">
              AI usage this session: <strong>{runs.total_tokens.toLocaleString()} tokens</strong> ·
              estimated cost <strong>{money(runs.total_estimated_cost_usd)}</strong> on {runs.model}
              {' '}(assumed ${runs.price_per_1m_tokens.input}/1M input, ${runs.price_per_1m_tokens.output}/1M output).
              Accountability only, <strong>not deducted from checking</strong>.
            </p>
          )}
        </section>

        <div className="grid">
          <section className="card">
            <h2>Agents live</h2>
            <ul className="agents">
              {AGENTS.map(a => {
                const mine = events.filter(e => e.agent === a)
                const last = mine[mine.length - 1]
                const busy = !!last && running.includes(last.ticket_id) && !['reply', 'done', 'error'].includes(last.kind)
                return (
                  <li key={a}>
                    <span className={`dot ${busy ? 'on' : ''}`} aria-hidden />
                    <strong>{LABEL[a]}</strong>{' '}
                    <span className="muted small">{busy ? `working on #${last.ticket_id}` : 'idle'}</span>
                    <div className="small">{last ? `#${last.ticket_id} ${shortLine(last)}` : '—'}</div>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="card">
            <h2>Summary · ticket #{selected}</h2>
            {current?.resolution && <p><strong>Boss's call:</strong> {current.resolution.decision}</p>}
            {ticketEvents.length === 0 ? <p className="muted">Press Play to run the team on this ticket.</p> : (
              <ul className="summary">
                {AGENTS.map(a => {
                  const mine = ticketEvents.filter(e => e.agent === a)
                  if (!mine.length) return null
                  const tools = [...new Set(mine.filter(e => e.kind === 'tool').map(e => e.tool))]
                  const asked = [...new Set(mine.filter(e => e.kind === 'delegate').map(e => LABEL[e.target!]))]
                  const reply = [...mine].reverse().find(e => e.kind === 'reply')
                  return (
                    <li key={a}>
                      <strong>{LABEL[a]}</strong>
                      {asked.length > 0 && <div className="small">Asked: {asked.join(', ')}</div>}
                      {tools.length > 0 && <div className="small">Tools: {tools.join(', ')}</div>}
                      {reply && <div className="small">{cut(reply.text, 220)}</div>}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>

        <section className="card">
          <h2>Accounts payable</h2>
          {payables && payables.items.length > 0 ? (
            <>
              <table className="table">
                <thead><tr><th>Due date</th><th>Vendor</th><th>Purchase</th><th>Ticket</th><th className="num">Amount</th></tr></thead>
                <tbody>
                  {payables.items.map(p => (
                    <tr key={p.draft_id}>
                      <td>{p.due_date}</td><td>{p.vendor}</td><td>{p.description}</td><td>#{p.ticket_id}</td>
                      <td className="num">{money(p.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>Checking {money(payables.checking)} − payable {money(payables.total)} = <strong className={payables.projected_balance < 0 ? 'bad' : ''}>projected savings {money(payables.projected_balance)}</strong> if no new money comes in.</p>
              <p className="small muted">{payables.note}</p>
            </>
          ) : <p className="muted small">No approved purchases waiting to be paid.</p>}
        </section>

        <section className="card">
          <h2>Human approvals</h2>
          {dismissed.size > 0 && <button className="link" onClick={() => setDismissed(new Set())}>Show closed banners again</button>}
          <ApprovalList payments={payments} drafts={drafts} balance={balance} free={payables?.projected_balance ?? balance} act={act} />
        </section>

        <section className="card">
          <h2>Activity feed · ticket #{selected}</h2>
          <ol className="feed">
            {ticketEvents.filter(e => e.kind !== 'tool_result').map(e => (
              <li key={e.id}><span className="muted small">{new Date(e.at).toLocaleTimeString()}</span> <strong>{LABEL[e.agent]}</strong> {shortLine(e)}</li>
            ))}
          </ol>
        </section>
      </main>

      <ApprovalBanners payments={payments} drafts={drafts} balance={balance} free={payables?.projected_balance ?? balance}
                       dismissed={dismissed} onClose={k => setDismissed(prev => new Set(prev).add(k))} act={act}
                       controls={
                         <div className="overlay-bar">
                           {running.map(id => (
                             <button key={id} className="secondary" onClick={() => act(`Run #${id} stopped.`, () => api.stop(id))}>■ Stop ticket #{id}</button>
                           ))}
                           <button className="danger" onClick={reset}>Reset database</button>
                         </div>
                       } />
    </>
  )
}

function RunMeter({ run }: { run: NonNullable<Ticket['run']> }) {
  const live = run.state === 'running'
  const pct = Math.min(100, (run.elapsed_s / run.estimated_total_s) * 100)
  const left = Math.max(0, run.estimated_total_s - run.elapsed_s)
  return (
    <div className="meter small">
      {live ? (
        <>
          <div className="bar" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${pct}%` }} />
          </div>
          <div>{clock(run.elapsed_s)} elapsed · {left > 0 ? `≈${clock(left)} left` : 'taking longer than usual…'}</div>
        </>
      ) : <div>Took {clock(run.elapsed_s)}</div>}
      <div className="muted">{run.total_tokens.toLocaleString()} tokens · ≈{money(run.estimated_cost_usd)} AI cost</div>
    </div>
  )
}

interface MoneyProps {
  payments: PaymentApproval[]
  drafts: Draft[]
  balance: number
  free: number
  act: Act
}

type PO = { vendor: string; sku: string; size: string; qty: number; total_cost: number; earliest_arrival_if_sent_today: string; blocked_by_open_invoices: number[] }

/** Blocking, stacked banners: one layer per payment or purchase waiting on Fran. */
function ApprovalBanners({ payments, drafts, balance, free, act, dismissed, onClose, controls }: MoneyProps & {
  dismissed: Set<string>
  onClose: (key: string) => void
  controls: React.ReactNode
}) {
  const layers = [
    ...payments.filter(p => p.status === 'pending').map(p => ({ key: `pay-${p.id}`, p })),
    ...drafts.filter(d => d.kind === 'purchase_order' && d.status === 'draft').map(d => ({ key: `po-${d.id}`, d })),
  ].filter(l => !dismissed.has(l.key))
  if (!layers.length) return null

  return (
    <div className="overlay" role="presentation">
      {controls}
      {layers.map((layer, i) => {
        const top = i === layers.length - 1
        let title: string, detail: string, amount: number, extra: string | null = null
        let shortBy: string | null = null
        let approve: () => Promise<unknown>, decline: () => Promise<unknown>
        if ('p' in layer) {
          const p = layer.p
          amount = p.amount
          title = p.kind === 'invoice' ? `Pay invoice #${p.ref_id}` : `Pay rent · lease #${p.ref_id}`
          detail = `${p.reason} (requested by ${p.requested_by})`
          if (amount > balance) shortBy = `Checking has ${money(balance)}, so this ${money(amount)} payment cannot be made.`
          approve = () => api.approvePayment(p.id)
          decline = () => api.rejectPayment(p.id)
        } else {
          const d = layer.d
          const po = d.payload as PO
          amount = po.total_cost
          title = `Approve purchase: ${po.qty}× ${po.sku} ${po.size}`
          detail = `From ${po.vendor} for ticket #${d.ticket_id}. Not paid now: it becomes an account payable due ${po.earliest_arrival_if_sent_today}.`
          if (po.blocked_by_open_invoices.length) extra = `Vendor is blocked by unpaid invoice #${po.blocked_by_open_invoices.join(', #')}; it won't ship until that's paid.`
          if (amount > free) shortBy = `Only ${money(free)} is free after accounts payable, so this ${money(amount)} purchase cannot be covered.`
          approve = () => api.decideDraft(d.id, 'approve')
          decline = () => api.decideDraft(d.id, 'reject')
        }
        return (
          <div key={layer.key} className="banner" role="alertdialog" aria-modal={top} aria-labelledby={`${layer.key}-t`}
               style={{ transform: `translate(${(layers.length - 1 - i) * -14}px, ${(layers.length - 1 - i) * -14}px)` }}>
            <div className="banner-eyebrow">Waiting for you, Fran · {i + 1} of {layers.length}</div>
            <h2 id={`${layer.key}-t`}>{title}</h2>
            <div className="banner-amount">{money(amount)}</div>
            <p>{detail}</p>
            {extra && <p className="warn">{extra}</p>}
            {shortBy && <p className="bad"><strong>NOT ENOUGH CASH.</strong> {shortBy} You can only decline it.</p>}
            <div className="row-btns">
              <button className="primary" disabled={!!shortBy || !top}
                      onClick={() => act(`${title} · approved.`, approve)}>Approve</button>
              <button className="secondary" disabled={!top} onClick={() => act(`${title} · declined.`, decline)}>Decline</button>
              {!shortBy && <button className="link" disabled={!top} onClick={() => onClose(layer.key)}>Close</button>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ApprovalList({ payments, drafts, balance, free, act }: MoneyProps) {
  const pending = payments.filter(p => p.status === 'pending')
  const decided = payments.filter(p => p.status !== 'pending')
  const orders = drafts.filter(d => d.kind === 'purchase_order')
  const messages = drafts.filter(d => d.kind === 'customer_message')

  return (
    <>
      <h3>Payments</h3>
      {pending.length === 0 && decided.length === 0 && <p className="muted small">No payments requested.</p>}
      {pending.map(p => {
        const short = p.amount > balance
        return (
          <div key={p.id} className={`item ${short ? 'blocked' : ''}`}>
            <div><strong>{money(p.amount)}</strong> · {p.kind === 'invoice' ? `Invoice #${p.ref_id}` : `Rent, lease #${p.ref_id}`} · asked by {p.requested_by}</div>
            <div className="small muted">{p.reason}</div>
            {short && <div className="bad"><strong>NOT ENOUGH CASH:</strong> needs {money(p.amount)}, checking has {money(balance)}.</div>}
            <div className="row-btns">
              <button className="primary" disabled={short} onClick={() => act(`Approval #${p.id} paid.`, () => api.approvePayment(p.id))}>Approve & pay</button>
              <button className="secondary" onClick={() => act(`Approval #${p.id} declined.`, () => api.rejectPayment(p.id))}>Decline</button>
            </div>
          </div>
        )
      })}
      {decided.map(p => (
        <div key={p.id} className={`item done ${p.status === 'refused' ? 'blocked' : ''}`}>
          {money(p.amount)} · {p.kind} #{p.ref_id} · <strong>{p.status.toUpperCase()}</strong>
          {p.status === 'refused' && <div className="bad small">{p.result}</div>}
        </div>
      ))}

      <h3>Purchase orders</h3>
      {orders.length === 0 && <p className="muted small">No purchase orders drafted.</p>}
      {orders.map(d => {
        const po = d.payload as PO
        const short = po.total_cost > free
        return (
          <div key={d.id} className={`item ${short && d.status === 'draft' ? 'blocked' : ''} ${d.status !== 'draft' ? 'done' : ''}`}>
            <div><strong>{po.qty}× {po.sku} {po.size}</strong> from {po.vendor} · {money(po.total_cost)} · ticket #{d.ticket_id}</div>
            <div className="small muted">Due on delivery: {po.earliest_arrival_if_sent_today}</div>
            {po.blocked_by_open_invoices.length > 0 && <div className="warn small">Vendor blocked by unpaid invoice #{po.blocked_by_open_invoices.join(', #')}.</div>}
            {short && d.status === 'draft' && <div className="bad"><strong>NOT ENOUGH CASH:</strong> costs {money(po.total_cost)}, only {money(free)} free after payables.</div>}
            {d.status === 'draft' ? (
              <div className="row-btns">
                <button className="primary" disabled={short} onClick={() => act(`Purchase #${d.id} approved.`, () => api.decideDraft(d.id, 'approve'))}>Approve purchase</button>
                <button className="secondary" onClick={() => act(`Purchase #${d.id} declined.`, () => api.decideDraft(d.id, 'reject'))}>Decline</button>
              </div>
            ) : <strong>{d.status.toUpperCase()}</strong>}
          </div>
        )
      })}

      <h3>Message drafts (never sent automatically)</h3>
      {messages.length === 0 && <p className="muted small">No message drafts.</p>}
      {messages.map(d => {
        const m = d.payload as { to: string; subject: string; body: string }
        return (
          <details key={d.id} className="item">
            <summary>To {m.to}: {m.subject} · ticket #{d.ticket_id} · <strong>{d.status}</strong></summary>
            <pre>{m.body}</pre>
            {d.status === 'draft' && (
              <div className="row-btns">
                <button className="primary" onClick={() => act(`Draft #${d.id} approved.`, () => api.decideDraft(d.id, 'approve'))}>Approve</button>
                <button className="secondary" onClick={() => act(`Draft #${d.id} declined.`, () => api.decideDraft(d.id, 'reject'))}>Decline</button>
              </div>
            )}
          </details>
        )
      })}
    </>
  )
}
