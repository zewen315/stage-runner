import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listWorkflows } from '../api.js'

export default function WorkflowsList() {
  const [workflows, setWorkflows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listWorkflows().then(setWorkflows).catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (workflows === null) return <p>Loading...</p>

  return (
    <div>
      <h1>Workflows</h1>
      {workflows.length === 0 ? (
        <p>No workflows found.</p>
      ) : (
        <ul className="list">
          {workflows.map((name) => (
            <li key={name}>
              <Link to={`/workflows/${name}`}>{name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
