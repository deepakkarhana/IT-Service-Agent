// Small presentational pieces shared by every screen.

const DECISION_STYLE = {
  RESOLVE: { cls: 'badge-green', label: 'RESOLVED' },
  CLARIFY: { cls: 'badge-amber', label: 'CLARIFICATION REQUIRED' },
  ESCALATE: { cls: 'badge-red', label: 'ESCALATED' },
  ROUTE_TO_OTHER_FUNCTION: { cls: 'badge-violet', label: 'ROUTED' },
  CREATE_TICKET: { cls: 'badge-blue', label: 'TICKET RAISED' },
}

const PRIORITY_STYLE = {
  HIGH: 'badge-red',
  MEDIUM: 'badge-amber',
  LOW: 'badge-slate',
}

export function DecisionBadge({ decision }) {
  const style = DECISION_STYLE[decision] || { cls: 'badge-slate', label: decision }
  return (
    <span className={`badge ${style.cls}`}>
      <span className="badge-dot" />
      {style.label}
    </span>
  )
}

export function PriorityBadge({ priority }) {
  return (
    <span className={`badge ${PRIORITY_STYLE[priority] || 'badge-slate'}`}>
      {priority} PRIORITY
    </span>
  )
}

export function StatusPill({ active }) {
  return (
    <span className={`badge ${active ? 'badge-blue' : 'badge-slate'}`}>
      {active ? 'ACTIVE' : 'CLOSED'}
    </span>
  )
}

export function Chip({ label, value }) {
  return (
    <span className="chip">
      {label}: <strong>{value}</strong>
    </span>
  )
}

export function Card({ title, hint, right, children }) {
  return (
    <section className="card">
      {(title || right) && (
        <div className="card-head">
          {title && <h3>{title}</h3>}
          {hint && <span className="hint">{hint}</span>}
          {right && <div style={{ marginLeft: 'auto' }}>{right}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}

export function ErrorNote({ message }) {
  if (!message) return null
  return <div className="alert-error">{message}</div>
}
