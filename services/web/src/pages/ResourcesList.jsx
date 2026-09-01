import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listResources } from '../api.js'

export default function ResourcesList() {
  const [resources, setResources] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listResources().then(setResources).catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (resources === null) return <p>Loading...</p>

  return (
    <div>
      <h1>Resources</h1>
      {resources.length === 0 ? (
        <p>No resources yet.</p>
      ) : (
        <ul className="list">
          {resources.map((r) => (
            <li key={r.name}>
              <Link to={`/resources/${r.name}`}>{r.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
