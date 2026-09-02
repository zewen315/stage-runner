import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getResource, listResources } from '../api.js'

export default function ResourcesList() {
  const [resources, setResources] = useState(null)
  const [current, setCurrent] = useState({})
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const rows = await listResources()
        if (cancelled) return
        setResources(rows)

        const snapshots = await Promise.all(rows.map((r) => getResource(r.name).catch(() => null)))
        if (cancelled) return
        setCurrent(Object.fromEntries(rows.map((r, i) => [r.name, snapshots[i]])))
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
  if (resources === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-wide">
      <h1>Resources</h1>
      {resources.length === 0 ? (
        <p className="muted">No resources found.</p>
      ) : (
        <div className="entity-list">
          {resources.map((r) => {
            const snapshot = current[r.name]
            return (
              <Link key={r.id} to={`/resources/${r.name}`} className="card entity-card entity-card-link">
                <div className="entity-card-top">
                  <span className="entity-name">{r.name}</span>
                  {snapshot ? (
                    <span className="status status-completed">current v{snapshot.version.version}</span>
                  ) : (
                    <span className="status status-skipped">no current version</span>
                  )}
                </div>
                {snapshot && (
                  <p className="muted entity-card-empty">promoted {formatTime(snapshot.version.created_at)}</p>
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
