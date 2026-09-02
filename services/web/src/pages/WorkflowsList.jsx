import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRuns, listWorkflows } from '../api.js'

export default function WorkflowsList() {
  const [workflows, setWorkflows] = useState(null)
  const [mostRecent, setMostRecent] = useState({})
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const names = await listWorkflows()
        if (cancelled) return
        setWorkflows(names)

        const runLists = await Promise.all(names.map((name) => listRuns(name, 1).catch(() => [])))
        if (cancelled) return
        setMostRecent(Object.fromEntries(names.map((name, i) => [name, runLists[i][0] || null])))
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
            const run = mostRecent[name]
            return (
              <Link key={name} to={`/workflows/${name}`} className="card entity-card entity-card-link">
                <div className="entity-card-top">
                  <span className="entity-name">{name}</span>
                  {run ? (
                    <span className={`status status-${run.status}`}>{run.status}</span>
                  ) : (
                    <span className="status status-skipped">no runs yet</span>
                  )}
                </div>
                {run && (
                  <p className="muted entity-card-empty">
                    run #{run.id} &middot; {formatTime(run.requested_at)}
                  </p>
                )}
              </Link>
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
