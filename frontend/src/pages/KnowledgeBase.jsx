import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, ErrorNote } from '../components/Badges.jsx'

export function KnowledgeBase() {
  const [policies, setPolicies] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .knowledgeBase()
      .then((data) => setPolicies(data.policies))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading knowledge base...</div>

  return (
    <>
      <ErrorNote message={error} />
      <p className="muted small">
        These {policies.length} entries are the agent's only source of business
        knowledge. Nothing outside this list is used to answer a request.
      </p>
      {policies.map((policy) => (
        <Card
          key={policy.id}
          title={`${policy.id} - ${policy.title}`}
          right={<span className="badge badge-slate">{policy.category}</span>}
        >
          <p>{policy.content}</p>
          <div className="section-label">Key points</div>
          <ul className="mb-0">
            {policy.key_points.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
          <div className="divider" />
          <p className="muted small mb-0">
            <strong>Owning function:</strong> {policy.owning_function}
          </p>
        </Card>
      ))}
    </>
  )
}
