import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getResource, listVersions, promote } from '../api.js'

export default function ResourceDetail() {
  const { name } = useParams()
  const [current, setCurrent] = useState(null)
  const [versions, setVersions] = useState(null)
  const [error, setError] = useState(null)
  const [promoting, setPromoting] = useState(null)

  function load() {
    listVersions(name).then(setVersions).catch((e) => setError(e.message))
    getResource(name)
      .then((snapshot) => setCurrent(snapshot.version.version))
      .catch(() => setCurrent(null)) // no current version promoted yet -- not an error
  }

  useEffect(load, [name])

  async function handlePromote(version) {
    setPromoting(version)
    try {
      await promote(name, version)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setPromoting(null)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (versions === null) return <p>Loading...</p>

  return (
    <div>
      <p>
        <Link to="/resources">&larr; Resources</Link>
      </p>
      <h1>{name}</h1>
      {versions.length === 0 ? (
        <p>No versions yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Created</th>
              <th>Test</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {[...versions].reverse().map((v) => (
              <tr key={v.id} className={v.version === current ? 'current' : ''}>
                <td>
                  {v.version} {v.version === current && <strong>(current)</strong>}
                </td>
                <td>{v.created_at}</td>
                <td>{v.is_test ? 'yes' : ''}</td>
                <td>
                  {v.version !== current && (
                    <button onClick={() => handlePromote(v.version)} disabled={promoting === v.version}>
                      {promoting === v.version ? 'Promoting...' : 'Promote'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
