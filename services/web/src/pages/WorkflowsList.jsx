import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listWorkflows } from '../api.js'

export default function WorkflowsList() {
  const [workflows, setWorkflows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    listWorkflows()
      .then((names) => {
        if (!cancelled) setWorkflows(names)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })

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
          {workflows.map((name) => (
            <Link key={name} to={`/workflows/${name}`} className="card entity-card entity-card-link">
              <span className="entity-name">{name}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
