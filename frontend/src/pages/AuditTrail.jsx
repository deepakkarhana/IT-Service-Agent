import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, ErrorNote } from '../components/Badges.jsx'
import { AuditTimeline, formatTime } from '../components/AuditTimeline.jsx'

// The API returns a flat, newest-first event list. Group it back into one block
// per interaction so the trail reads as "what the agent did for this request".
function groupByInteraction(events) {
  const groups = new Map()
  for (const event of events) {
    if (!groups.has(event.interaction_id)) groups.set(event.interaction_id, [])
    groups.get(event.interaction_id).push(event)
  }
  return [...groups.entries()].map(([id, items]) => ({
    interactionId: id,
    events: [...items].sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
  }))
}

export function AuditTrail({ refreshKey, onDataChanged }) {
  const [groups, setGroups] = useState([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api
      .audit()
      .then((data) => {
        setGroups(groupByInteraction(data.events))
        setTotal(data.total)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [refreshKey])

  async function reset() {
    try {
      await api.resetRuntime()
      onDataChanged?.()
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) return <div className="loading">Loading audit trail...</div>

  return (
    <>
      <ErrorNote message={error} />
      <Card
        title="Audit trail"
        hint={`${total} events recorded in this session`}
        right={
          <button className="btn btn-ghost" onClick={reset}>
            Clear prototype records
          </button>
        }
      >
        {!groups.length ? (
          <div className="empty">
            No interactions yet. Submit a request and every stage will be recorded here.
          </div>
        ) : (
          groups.map((group) => {
            const first = group.events[0]
            const decision = group.events.find((e) => e.stage === 'decision')
            const ticket = group.events.find(
              (e) => e.stage === 'ticket_created' || e.stage === 'escalation_raised'
            )
            return (
              <div className="audit-group" key={group.interactionId}>
                <div className="audit-group-head">
                  <strong className="mono">{first.request_id}</strong>
                  <span className="muted">{first.employee}</span>
                  <span className="muted">{formatTime(first.timestamp)}</span>
                  {decision && (
                    <span className="badge badge-blue">{decision.data?.decision}</span>
                  )}
                  {ticket && (
                    <span className="badge badge-slate mono">{ticket.data?.ticket_id}</span>
                  )}
                  <span className="muted small mono" style={{ marginLeft: 'auto' }}>
                    {group.interactionId}
                  </span>
                </div>
                <div className="audit-group-body">
                  <AuditTimeline events={group.events} />
                </div>
              </div>
            )
          })
        )}
      </Card>
      <p className="muted small">
        The audit trail is written to <code>data/runtime/audit_log.json</code>, so it
        survives a backend restart. "Clear prototype records" removes the tickets and
        audit events this prototype created; the supplied data pack is never modified.
      </p>
    </>
  )
}
