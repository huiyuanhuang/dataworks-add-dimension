const API_BASE = ''

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json()
}

export default {
  getProjects: () => request('/api/projects/list'),
  analyze: (data) => request('/api/analysis/analyze', { method: 'POST', body: JSON.stringify(data) }),
  modify: (data) => request('/api/analysis/modify', { method: 'POST', body: JSON.stringify(data) }),
  saveDraft: (data) => request('/api/execution/save-draft', { method: 'POST', body: JSON.stringify(data) }),
  alterTable: (data) => request('/api/execution/alter-table', { method: 'POST', body: JSON.stringify(data) }),
  generateBackfill: (data) => request('/api/execution/generate-backfill', { method: 'POST', body: JSON.stringify(data) }),
  executeBackfill: (data) => request('/api/execution/execute-backfill', { method: 'POST', body: JSON.stringify(data) }),
  syncBI: (data) => request('/api/execution/sync-bi', { method: 'POST', body: JSON.stringify(data) }),
  submitFile: (data) => request('/api/execution/submit-file', { method: 'POST', body: JSON.stringify(data) }),
  modifyDownstreamFilter: (data) => request('/api/downstream/modify-downstream-filter', { method: 'POST', body: JSON.stringify(data) }),
}
