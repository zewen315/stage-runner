import { Fragment, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getResource, getVersion, listVersions, promote } from '../api.js'

export default function ResourceDetail() {
  const { name } = useParams()
  const [searchParams] = useSearchParams()
  const [current, setCurrent] = useState(null)
  const [versions, setVersions] = useState(null)
  const [error, setError] = useState(null)
  const [promoting, setPromoting] = useState(null)

  const requestedVersion = Number(searchParams.get('version')) || null
  const [expanded, setExpanded] = useState(requestedVersion)
  const [values, setValues] = useState({}) // version -> value, fetched lazily
  const [valueError, setValueError] = useState(null)

  function load() {
    listVersions(name).then(setVersions).catch((e) => setError(e.message))
    getResource(name)
      .then((snapshot) => setCurrent(snapshot.version.version))
      .catch(() => setCurrent(null)) // no current version promoted yet -- not an error
  }

  useEffect(load, [name])

  useEffect(() => {
    if (expanded !== null && !(expanded in values)) {
      loadValue(expanded)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded])

  function loadValue(version) {
    setValueError(null)
    getVersion(name, version)
      .then((snapshot) => setValues((prev) => ({ ...prev, [version]: snapshot.value })))
      .catch((e) => setValueError(e.message))
  }

  function toggle(version) {
    setExpanded((prev) => (prev === version ? null : version))
  }

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
  if (versions === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-narrow">
      <p>
        <Link to="/" className="back-link">
          &larr; Dashboard
        </Link>
      </p>
      <h1>{name}</h1>
      {versions.length === 0 ? (
        <p className="muted">No versions yet.</p>
      ) : (
        <div className="card">
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
                <Fragment key={v.id}>
                  <tr className={v.version === current ? 'current-row' : ''}>
                    <td>
                      {v.version} {v.version === current && <strong>(current)</strong>}
                    </td>
                    <td>{v.created_at}</td>
                    <td>{v.is_test ? 'yes' : ''}</td>
                    <td className="row-actions">
                      <button className="btn-ghost" onClick={() => toggle(v.version)}>
                        {expanded === v.version ? 'Hide' : 'View'}
                      </button>
                      {v.version !== current && (
                        <button
                          className="btn-ghost"
                          onClick={() => handlePromote(v.version)}
                          disabled={promoting === v.version}
                        >
                          {promoting === v.version ? 'Promoting...' : 'Promote'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded === v.version && (
                    <tr>
                      <td colSpan={4}>
                        {valueError ? (
                          <p className="error">{valueError}</p>
                        ) : v.version in values ? (
                          <pre className="value-view">{JSON.stringify(values[v.version], null, 2)}</pre>
                        ) : (
                          <p className="muted">Loading value...</p>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
