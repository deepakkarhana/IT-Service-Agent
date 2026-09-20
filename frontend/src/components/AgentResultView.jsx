// Renders one structured agent result. Used by both the New Request screen and
// the Request Queue detail panel, so the two always show the same thing.

import { Card, Chip, DecisionBadge, PriorityBadge, StatusPill } from './Badges.jsx'
import { AuditTimeline } from './AuditTimeline.jsx'

const ENTITY_LABEL = {
  employee_type: 'Employment type',
  account_locked_out: 'Account locked out',
  failed_attempts: 'Failed attempts',
  credentials_expired: 'Credentials expired',
  new_access_request: 'New access request',
  existing_account: 'Account already exists',
  asset_type: 'Asset type',
  asset_age_years: 'Asset age (years)',
  reported_hardware_failure: 'Total failure reported',
  hardware_symptom: 'Reported symptom',
  asset_tag: 'Asset tag',
  already_tried_basic_steps: 'Basic steps already tried',
  software_name: 'Software',
  in_approved_catalog: 'In approved catalog',
  requests_quota_increase: 'Quota increase requested',
  remote_days_per_week: 'Remote days per week',
  already_forwarded: 'Already forwarded to others',
}

function formatValue(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  if (typeof value === 'string') return value.replace(/_/g, '-')
  return String(value)
}

function ExtractedFacts({ entities }) {
  const facts = Object.entries(entities || {}).filter(
    ([, value]) => value !== null && value !== undefined
  )
  if (!facts.length) {
    return (
      <p className="muted small mb-0">
        No specific facts were stated in the message.
      </p>
    )
  }
  return (
    <div className="fact-list">
      {facts.map(([key, value]) => (
        <Chip key={key} label={ENTITY_LABEL[key] || key} value={formatValue(value)} />
      ))}
    </div>
  )
}

function PolicyQuotes({ points }) {
  if (!points?.length) {
    return (
      <p className="muted small mb-0">
        No policy in the supplied knowledge base covers this request.
      </p>
    )
  }
  return (
    <>
      {points.map((point, index) => (
        <div className="policy-quote" key={`${point.source_id}-${index}`}>
          <span className="src">{point.source_id}</span>
          <p>{point.text}</p>
        </div>
      ))}
    </>
  )
}

export function AgentResultView({ result }) {
  if (!result) return null
  const { response, understanding, ticket, policy_conflict: conflict } = result

  return (
    <>
      <div className={`decision-banner ${result.decision}`}>
        <div>
          <div className="decision-title">Decision</div>
          <div className="decision-meta">{understanding.intent}</div>
        </div>
        <div className="row-gap" style={{ marginLeft: 'auto' }}>
          <DecisionBadge decision={result.decision} />
          <PriorityBadge priority={result.priority} />
          <span className="chip">
            Assigned to: <strong>{result.assigned_team}</strong>
          </span>
          <span className="chip">
            {result.mode === 'llm' ? 'LLM mode' : 'Demo / fallback mode'}
          </span>
        </div>
      </div>

      <div className="grid-2">
        <div>
          <Card title="Agent response">
            <div className="response-block">
              <div className="section-label">What I understood</div>
              <p className="mb-0">{response.understood}</p>
            </div>

            <div className="response-block">
              <div className="section-label">What the policy says</div>
              <PolicyQuotes points={response.policy_says} />
            </div>

            {conflict?.detected && (
              <div className="response-block">
                <div className="notice conflict">
                  <span className="notice-title">
                    Conflicting policy guidance - not resolved by the agent
                  </span>
                  <p>{conflict.summary}</p>
                  <p className="mb-0">
                    <strong>How it is handled:</strong> {conflict.resolution_path}
                  </p>
                </div>
              </div>
            )}

            {response.notice && !conflict?.detected && (
              <div className="response-block">
                <div className="notice">
                  <span className="notice-title">Important</span>
                  <p className="mb-0">{response.notice}</p>
                </div>
              </div>
            )}

            <div className="response-block">
              <div className="section-label">What happens next</div>
              <p className="mb-0">{response.what_happens_next}</p>
            </div>

            {response.your_actions?.length > 0 && (
              <div className="response-block">
                <div className="section-label">What you need to do</div>
                <ul className="mb-0">
                  {response.your_actions.map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.clarifying_question && (
              <div className="response-block">
                <div className="question-box">
                  <strong>Follow-up question:</strong> {result.clarifying_question}
                </div>
              </div>
            )}
          </Card>

          <Card title="Why this decision" hint="Reasoning based on the retrieved policy">
            <p className="mb-0">{result.decision_reason}</p>
            <div className="divider" />
            <dl className="kv">
              <dt>Next action</dt>
              <dd>{result.next_action}</dd>
              <dt>Assigned team</dt>
              <dd>{result.assigned_team}</dd>
              <dt>Risk level</dt>
              <dd>{result.risk_level}</dd>
            </dl>
          </Card>

          <Card title="Audit trail" hint="Every stage of this interaction">
            <AuditTimeline events={result.audit_events} />
          </Card>
        </div>

        <div>
          <Card title="Understanding" hint="Step 1 of the pipeline">
            <dl className="kv">
              <dt>Issue category</dt>
              <dd>{understanding.category}</dd>
              <dt>Detected topic</dt>
              <dd className="mono small">{understanding.topic}</dd>
              <dt>Intent</dt>
              <dd>{understanding.intent}</dd>
              <dt>Risk level</dt>
              <dd>{understanding.risk_level}</dd>
              {understanding.urgency_stated && (
                <>
                  <dt>Urgency stated</dt>
                  <dd>"{understanding.urgency_stated}"</dd>
                </>
              )}
              <dt>Classified by</dt>
              <dd className="mono small">{understanding.classification_source}</dd>
            </dl>
            <div className="divider" />
            <div className="section-label">Facts taken from the message</div>
            <ExtractedFacts entities={understanding.entities} />
            {understanding.missing_information?.length > 0 && (
              <>
                <div className="divider" />
                <div className="section-label">Missing information</div>
                <ul className="mb-0 small">
                  {understanding.missing_information.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card title="Sources" hint="Retrieved from the IT knowledge base">
            {result.sources?.length ? (
              result.sources.map((source) => (
                <div className="source-card" key={source.id}>
                  <div className="source-head">
                    <span className="source-id">{source.id}</span>
                    <span className="source-title">{source.title}</span>
                    <span
                      className={`badge ${
                        source.relevance === 'authoritative' ? 'badge-blue' : 'badge-slate'
                      }`}
                      style={{ marginLeft: 'auto' }}
                    >
                      {source.relevance}
                    </span>
                  </div>
                  <p className="source-text">{source.excerpt}</p>
                </div>
              ))
            ) : (
              <div className="empty">
                No policy in the supplied knowledge base matched this request.
              </div>
            )}
          </Card>

          {result.related_tickets?.length > 0 && (
            <Card title="Ticket context" hint="Existing cases on this topic">
              <div className="stack">
                {result.related_tickets.map((item) => (
                  <div className="source-card" key={item.ticket_id}>
                    <div className="source-head">
                      <span className="source-id">{item.ticket_id}</span>
                      <StatusPill active={item.active} />
                    </div>
                    <p className="source-text">{item.issue_summary}</p>
                    <p className="source-text">
                      <strong>Status:</strong> {item.status}
                    </p>
                    <p className="source-text mb-0">
                      <em>{item.note}</em>
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card
            title="Ticket"
            hint={ticket ? 'Created by this interaction' : 'None required'}
          >
            {ticket ? (
              <dl className="kv">
                <dt>Ticket ID</dt>
                <dd className="mono">
                  <strong>{ticket.ticket_id}</strong>{' '}
                  <span className="badge badge-slate">prototype-generated</span>
                </dd>
                <dt>Employee</dt>
                <dd>{ticket.employee}</dd>
                <dt>Issue</dt>
                <dd>{ticket.issue_summary}</dd>
                <dt>Category</dt>
                <dd>{ticket.category}</dd>
                <dt>Priority</dt>
                <dd>{ticket.priority}</dd>
                <dt>Decision</dt>
                <dd>{ticket.decision}</dd>
                <dt>Next action</dt>
                <dd>{ticket.next_action}</dd>
                <dt>Status</dt>
                <dd>{ticket.status}</dd>
                <dt>Assigned team</dt>
                <dd>{ticket.assigned_team}</dd>
                <dt>Source policy</dt>
                <dd>{ticket.source_policy?.join(', ') || 'None'}</dd>
                <dt>Created at</dt>
                <dd className="small">{ticket.created_at}</dd>
              </dl>
            ) : (
              <div className="empty">
                No ticket was raised for this interaction
                {result.decision === 'CLARIFY'
                  ? ' - the agent is waiting on information from the employee.'
                  : ' - it was resolved without IT action.'}
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
