// Single place where the UI talks to the backend.
// Every call returns parsed JSON or throws an Error with a readable message,
// so the pages only ever deal with { data, error, loading }.

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (err) {
    throw new Error(
      'Could not reach the agent API. Is the backend running on port 8000?'
    )
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? detail[0].msg
          : `Request failed (HTTP ${response.status}).`
    throw new Error(message)
  }
  return payload
}

export const api = {
  health: () => request('/api/health'),
  capabilities: () => request('/api/capabilities'),
  demoSamples: () => request('/api/demo-samples'),
  knowledgeBase: () => request('/api/knowledge-base'),
  requests: () => request('/api/requests'),
  tickets: () => request('/api/tickets'),
  audit: () => request('/api/audit'),
  resetRuntime: () => request('/api/runtime/reset', { method: 'POST' }),
  handle: (body) =>
    request('/api/agent/handle', { method: 'POST', body: JSON.stringify(body) }),
  triage: (requestId) =>
    request(`/api/requests/${requestId}/triage`, { method: 'POST' }),
}
