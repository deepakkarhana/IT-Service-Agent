import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, DecisionBadge, ErrorNote, PriorityBadge } from '../components/Badges.jsx'
import { AgentResultView } from '../components/AgentResultView.jsx'

export function RequestQueue({ onDataChanged }) {
  const [rows, setRows] = useState([])
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .requests()
      .then((data) => setRows(data.requests))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function select(row) {
    setSelected(row)
    setResult(null)
    setError('')
  }

  async function runAgent() {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      const data = await api.triage(selected.request_id)
      setResult(data)
      onDataChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="loading">Loading request queue...</div>

  return (
    <>
      <ErrorNote message={error} />
      <Card
        title="Employee request queue"
        hint="15 requests from the supplied data pack. The decision column is the agent's deterministic triage."
      >
        <table>
          <thead>
            <tr>
              <th>Request</th>
              <th>Employee</th>
              <th>Issue</th>
              <th>Existing action</th>
              <th>Agent decision</th>
              <th>Priority</th>
              <th>Assigned team</th>
              <th>Sources</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.request_id}
                className={`clickable ${selected?.request_id === row.request_id ? 'selected' : ''}`}
                onClick={() => select(row)}
              >
                <td className="cell-id">{row.request_id}</td>
                <td>{row.employee}</td>
                <td className="cell-issue">{row.request}</td>
                <td className="small muted">{row.initial_action || '-'}</td>
                <td>
                  <DecisionBadge decision={row.preview.decision} />
                  {row.preview.conflict && (
                    <div className="small" style={{ color: 'var(--red-fg)', marginTop: 4 }}>
                      policy conflict
                    </div>
                  )}
                </td>
                <td>
                  <PriorityBadge priority={row.preview.priority} />
                </td>
                <td className="small">{row.preview.assigned_team}</td>
                <td className="small mono">{row.preview.sources.join(', ') || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {selected && (
        <Card
          title={`${selected.request_id} - ${selected.employee}`}
          hint={`Opened ${selected.date_opened}`}
          right={
            <button className="btn btn-primary" onClick={runAgent} disabled={busy}>
              {busy && <span className="spinner" />}
              {busy ? 'Running...' : 'Run full agent on this request'}
            </button>
          }
        >
          <dl className="kv">
            <dt>Original request</dt>
            <dd>{selected.request}</dd>
            <dt>Employee</dt>
            <dd>
              {selected.employee} <span className="muted small">({selected.email})</span>
            </dd>
            <dt>Existing action</dt>
            <dd>{selected.initial_action || 'None recorded in the data pack'}</dd>
            <dt>Triage preview</dt>
            <dd>
              {selected.preview.intent} - {selected.preview.decision} -{' '}
              {selected.preview.assigned_team}
            </dd>
          </dl>
          {!result && (
            <p className="muted small" style={{ marginTop: 12, marginBottom: 0 }}>
              The preview above is computed by the deterministic rules only. Run the
              full agent to retrieve sources, create any ticket and write the audit
              trail.
            </p>
          )}
        </Card>
      )}

      {result && <AgentResultView result={result} />}
    </>
  )
}
