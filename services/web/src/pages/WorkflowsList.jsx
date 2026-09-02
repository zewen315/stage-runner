import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRuns, listWorkflows } from '../api.js'
import { useNewRunModal } from '../NewRunModalContext.jsx'

const RECENT_LIMIT = 5

export default function WorkflowsList() {
  const { open } = useNewRunModal()
  const [workflows, setWorkflows] = useState(null)
  const [runsByWorkflow, setRunsByWorkflow] = useState({})
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const names = await listWorkflows()
        if (cancelled) return
        setWorkflows(names)

        const runsList = await Promise.all(names.map((name) => listRuns(name, RECENT_LIMIT).catch(() => [])))
        if (cancelled) return
        setRunsByWorkflow(Object.fromEntries(names.map((name, i) => [name, runsList[i]])))
      } catch (e) {
        if (!cancelled) setError(e.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <p className="error">{error}</p>
  if (workflows === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-wide">
      <h1>Workflows</h1>
      {workflows.length === 0 ? (
        <p className="muted">No workflows found.</p>
      ) : (
        <div className="entity-list">
          {workflows.map((name) => {
            const runs = runsByWorkflow[name] || []
            return (
              <div key={name} className="card entity-card">
                <div className="entity-card-top">
                  <span className="workflow-pill">{name}</span>
                  <button className="btn-ghost" onClick={() => open({ workflow: name })}>
                    New run
                  </button>
                </div>
                {runs.length === 0 ? (
                  <p className="muted entity-card-empty">No runs yet.</p>
                ) : (
                  <div className="mini-run-list">
                    {runs.map((r) => (
                      <Link key={r.id} to={`/workflows/${name}/runs/${r.id}`} className="mini-run-row">
                        <span className={`status status-${r.status}`}>{r.status}</span>
                        <span>run #{r.id}</span>
                        <span className="mini-run-time">{formatTime(r.requested_at)}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function formatTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
