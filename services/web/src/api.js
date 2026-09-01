// Thin fetch wrappers, one per endpoint. Always same-origin (served by
// `gateway` alongside the APIs in production; proxied by Vite in dev) so
// there's no base-URL configuration, unlike the CLI.

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // response wasn't JSON -- keep statusText
    }
    throw new Error(detail)
  }

  if (response.status === 204) return null
  return response.json()
}

export function listWorkflows() {
  return request('/workflows')
}

export function listRuns(workflowName, limit = 50) {
  return request(`/workflows/${workflowName}/runs?limit=${limit}`)
}

export function getRun(workflowName, runId) {
  return request(`/workflows/${workflowName}/runs/${runId}`)
}

export function listStageRuns(workflowName, runId) {
  return request(`/workflows/${workflowName}/runs/${runId}/stage-runs`)
}

export function requestRun(workflowName, body) {
  return request(`/workflows/${workflowName}/runs`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getSchedule(workflowName, scheduleId) {
  return request(`/workflows/${workflowName}/schedules/${scheduleId}`)
}

export function listPendingSchedules(workflowName) {
  return request(`/workflows/${workflowName}/schedules`)
}

export function listResources() {
  return request('/resources')
}

export function getResource(name) {
  return request(`/resources/${name}`)
}

export function listVersions(name) {
  return request(`/resources/${name}/versions`)
}

export function getVersion(name, version) {
  return request(`/resources/${name}/versions/${version}`)
}

export function promote(name, version) {
  return request(`/resources/${name}/promotions`, {
    method: 'POST',
    body: JSON.stringify({ version }),
  })
}
