import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, ErrorNote } from '../components/Badges.jsx'
import { AgentResultView } from '../components/AgentResultView.jsx'

export function NewRequest({ onDataChanged }) {
  const [message, setMessage] = useState('')
  const [capabilities, setCapabilities] = useState([])
  const [samples, setSamples] = useState([])
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.capabilities().then(setCapabilities).catch(() => setCapabilities([]))
    api.demoSamples().then(setSamples).catch(() => setSamples([]))
  }, [])

  async function submit(event) {
    event?.preventDefault()
    const text = message.trim()
    if (!text) {
      setError('Please describe the issue before submitting.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await api.handle({ message: text, employee: 'Employee (demo user)' })
      setResult(data)
      onDataChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function clearAll() {
    setMessage('')
    setResult(null)
    setError('')
  }

  return (
    <>
      <div className="capabilities">
        {capabilities.map((capability, index) => (
          <div className="capability" key={capability.title}>
            <div className="step">STEP {index + 1}</div>
            <h4>{capability.title}</h4>
            <p>{capability.detail}</p>
          </div>
        ))}
      </div>

      <Card title="How can we help?" hint="Describe your IT issue in your own words">
        <ErrorNote message={error} />
        <form onSubmit={submit}>
          <textarea
            rows={4}
            value={message}
            placeholder="For example: My VPN stopped working. It says my credentials expired."
            onChange={(event) => setMessage(event.target.value)}
          />
          <div className="btn-row" style={{ marginTop: 12 }}>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy && <span className="spinner" />}
              {busy ? 'Agent working...' : 'Submit request'}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={clearAll}
              disabled={busy}
            >
              Clear
            </button>
          </div>
        </form>

        <div className="divider" />
        <div className="section-label">Demo requests</div>
        <div className="sample-row">
          {samples.map((sample) => (
            <button
              className="sample"
              key={sample.label}
              type="button"
              onClick={() => {
                setMessage(sample.text)
                setError('')
              }}
            >
              {sample.label}
              <span className="sample-hint">{sample.hint}</span>
            </button>
          ))}
        </div>
      </Card>

      {result && <AgentResultView result={result} />}
    </>
  )
}
