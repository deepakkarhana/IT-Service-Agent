import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { NewRequest } from './pages/NewRequest.jsx'
import { RequestQueue } from './pages/RequestQueue.jsx'
import { Tickets } from './pages/Tickets.jsx'
import { KnowledgeBase } from './pages/KnowledgeBase.jsx'
import { AuditTrail } from './pages/AuditTrail.jsx'

const PAGES = [
  { key: 'new', label: 'New Request', title: 'New Request',
    sub: 'Describe an issue and see how the agent decides what happens next.' },
  { key: 'queue', label: 'Request Queue', title: 'Request Queue',
    sub: 'Employee requests from the supplied data pack, with the agent triage for each.' },
  { key: 'tickets', label: 'Tickets', title: 'Tickets',
    sub: 'Active cases that need action, and closed tickets kept as history.' },
  { key: 'kb', label: 'Knowledge Base', title: 'Knowledge Base',
    sub: 'The IT policies the agent is allowed to answer from.' },
  { key: 'audit', label: 'Audit Trail', title: 'Audit Trail',
    sub: 'A timestamped record of every stage of every interaction.' },
]

export default function App() {
  const [page, setPage] = useState('new')
  const [health, setHealth] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [])

  // Pages that show stored state re-fetch when the agent writes something.
  const onDataChanged = useCallback(() => setRefreshKey((key) => key + 1), [])

  const current = PAGES.find((item) => item.key === page)
  const llmMode = health?.mode === 'llm'

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <span className="brand-logo">IT</span>
            IT Service Agent
          </div>
          <div className="brand-sub">Internal support assistant</div>
        </div>
        <nav className="nav">
          {PAGES.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          Prototype for an internal IT service desk.
          <br />
          Answers come only from the supplied IT knowledge base.
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{current.title}</h1>
            <div className="topbar-sub">{current.sub}</div>
          </div>
          <div className="topbar-right">
            {health?.status === 'down' ? (
              <span className="badge badge-red">API unavailable</span>
            ) : (
              <span
                className={`badge ${llmMode ? 'badge-green' : 'badge-slate'}`}
                title={health?.mode_detail || ''}
              >
                {llmMode ? `LLM mode - ${health.model}` : 'Demo / fallback mode'}
              </span>
            )}
          </div>
        </header>

        <div className="content">
          {health?.status === 'down' && (
            <div className="alert-error">
              The backend API is not reachable. Start it with{' '}
              <code>uvicorn backend.app.main:app --port 8020</code> from the project
              root, then reload this page.
            </div>
          )}
          {page === 'new' && <NewRequest onDataChanged={onDataChanged} />}
          {page === 'queue' && <RequestQueue onDataChanged={onDataChanged} />}
          {page === 'tickets' && <Tickets refreshKey={refreshKey} />}
          {page === 'kb' && <KnowledgeBase />}
          {page === 'audit' && (
            <AuditTrail refreshKey={refreshKey} onDataChanged={onDataChanged} />
          )}
        </div>
      </main>
    </div>
  )
}
