// Renders the agent's audit events as a vertical timeline.

const STAGE_LABEL = {
  request_received: 'Request received',
  understanding: 'Intent detected',
  safety_override: 'Safety override applied',
  retrieval: 'Knowledge base retrieval',
  ticket_context: 'Ticket context retrieved',
  policy_evaluation: 'Policy evaluated',
  policy_conflict: 'Policy conflict detected',
  decision: 'Decision made',
  response_generated: 'Response generated',
  ticket_created: 'Ticket created',
  escalation_raised: 'Escalation raised',
  no_ticket_required: 'No ticket required',
  audit_recorded: 'Audit record created',
}

const ALERT_STAGES = ['policy_conflict', 'escalation_raised', 'safety_override']

export function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

export function AuditTimeline({ events }) {
  if (!events?.length) {
    return <div className="empty">No audit events recorded yet.</div>
  }
  return (
    <div className="timeline">
      {events.map((event, index) => {
        const alert = ALERT_STAGES.includes(event.stage)
        const done = event.stage === 'audit_recorded'
        return (
          <div className="tl-item" key={`${event.timestamp}-${index}`}>
            <span className={`tl-dot ${alert ? 'alert' : done ? 'done' : ''}`} />
            <div className="tl-time">{formatTime(event.timestamp)}</div>
            <div className="tl-stage">{STAGE_LABEL[event.stage] || event.stage}</div>
            <div className="tl-detail">{event.detail}</div>
          </div>
        )
      })}
    </div>
  )
}
