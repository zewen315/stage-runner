import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getDependencies, getResource, getVersion, listVersions, promote } from '../api.js'

export default function ResourceDetail() {
  const { name } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [current, setCurrent] = useState(null)
  const [versions, setVersions] = useState(null)
  const [error, setError] = useState(null)
  const [promoting, setPromoting] = useState(null)

  const requestedVersion = Number(searchParams.get('version')) || null
  const [expanded, setExpanded] = useState(requestedVersion)
  const [details, setDetails] = useState({}) // version -> { value, dependencies }
  const [detailsError, setDetailsError] = useState(null)

  function load() {
    listVersions(name).then(setVersions).catch((e) => setError(e.message))
    getResource(name)
      .then((snapshot) => setCurrent(snapshot.version.version))
      .catch(() => setCurrent(null)) // no current version promoted yet -- not an error
  }

  useEffect(load, [name])

  useEffect(() => {
    if (expanded !== null && !(expanded in details)) {
      loadDetails(expanded)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded])

  function loadDetails(version) {
    setDetailsError(null)
    Promise.all([getVersion(name, version), getDependencies(name, version)])
      .then(([snapshot, dependencies]) => {
        setDetails((prev) => ({ ...prev, [version]: { value: snapshot.value, dependencies } }))
      })
      .catch((e) => setDetailsError(e.message))
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
        <button className="back-link link-button" onClick={() => navigate(-1)}>
          &larr; Back
        </button>
      </p>
      <h1>{name}</h1>
      {versions.length === 0 ? (
        <p className="muted">No versions yet.</p>
      ) : (
        <div className="version-list">
          {[...versions].reverse().map((v) => {
            const isExpanded = expanded === v.version
            const detail = details[v.version]
            return (
              <div key={v.id} className={`card version-card ${v.version === current ? 'current-card' : ''}`}>
                <div className="version-card-top">
                  <div className="version-card-title">
                    <span className="version-number">v{v.version}</span>
                    {v.version === current && <span className="status status-completed">current</span>}
                    <span className={`status ${v.validation_error ? 'status-failed' : 'status-completed'}`}>
                      {v.validation_error ? 'invalid' : 'valid'}
                    </span>
                    {v.is_test && <span className="status status-requested">test</span>}
                  </div>
                  <span className="version-time">{formatTime(v.created_at)}</span>
                </div>

                <div className="row-actions">
                  <button className="btn-ghost" onClick={() => toggle(v.version)}>
                    {isExpanded ? 'Hide' : 'View'}
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
                </div>

                {isExpanded && (
                  <div className="version-body">
                    {v.validation_error && <p className="error">{v.validation_error}</p>}
                    {detailsError ? (
                      <p className="error">{detailsError}</p>
                    ) : detail ? (
                      <>
                        <p className="version-body-label">Dependencies</p>
                        {detail.dependencies.length === 0 ? (
                          <p className="muted">(none recorded)</p>
                        ) : (
                          <p>
                            {detail.dependencies.map((dep, i) => (
                              <span key={dep.id}>
                                {i > 0 && ', '}
                                <Link to={`/resources/${dep.name}?version=${dep.version}`}>
                                  {dep.name}:{dep.version}
                                </Link>
                              </span>
                            ))}
                          </p>
                        )}
                        <p className="version-body-label">Value</p>
                        <pre className="value-view">{JSON.stringify(detail.value, null, 2)}</pre>
                      </>
                    ) : (
                      <p className="muted">Loading...</p>
                    )}
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
  return iso ? iso.slice(0, 19) : ''
}
