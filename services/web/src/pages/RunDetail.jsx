import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getRun, listStageRuns } from '../api.js'

const TERMINAL = new Set(['completed', 'failed'])

export default function RunDetail() {
  const { name, runId } = useParams()
  const [run, setRun] = useState(null)
  const [stageRuns, setStageRuns] = useState([])
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [r, sr] = await Promise.all([getRun(name, runId), listStageRuns(name, runId)])
        if (cancelled) return
        setRun(r)
        setStageRuns(sr)
        if (TERMINAL.has(r.status) && intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
      } catch (e) {
        if (!cancelled) setError(e.message)
      }
    }

    load()
    intervalRef.current = setInterval(load, 2000)

    return () => {
      cancelled = true
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [name, runId])

  if (error) return <p className="error">{error}</p>
  if (!run) return <p className="muted">Loading...</p>

  return (
    <div className="page-narrow">
      <p>
        <Link to="/" className="back-link">
          &larr; Dashboard
        </Link>
      </p>

      <div className="run-header">
        <div>
          <span className="workflow-pill">{run.workflow_name}</span>
          <h1>Run #{run.id}</h1>
        </div>
        <span className={`status status-lg status-${run.status}`}>{run.status}</span>
      </div>

      <div className="card">
        <dl className="meta">
          <dt>Requested</dt>
          <dd>{formatTime(run.requested_at)}</dd>
          <dt>Started</dt>
          <dd>{formatTime(run.started_at) || '—'}</dd>
          <dt>Finished</dt>
          <dd>{formatTime(run.finished_at) || '—'}</dd>
          <dt>Start from</dt>
          <dd>{run.start_from || '(natural roots)'}</dd>
          <dt>Stop after</dt>
          <dd>{run.stop_after || '(run to completion)'}</dd>
          <dt>Promote</dt>
          <dd>{String(run.promote)}</dd>
        </dl>
        {run.error && <p className="error run-error">{run.error}</p>}
      </div>

      <h2>Stages</h2>
      <div className="stage-list">
        {stageRuns.map((sr) => (
          <div key={sr.id} className={`stage-card status-border-${sr.status}`}>
            <div className="stage-card-top">
              <span className="stage-name">{sr.stage_name}</span>
              <span className={`status status-${sr.status}`}>{sr.status}</span>
            </div>
            <div className="stage-card-meta">
              <span>in: {formatResources(sr.input_versions)}</span>
              <span>
                out: {sr.output_version != null ? <ResourceLink name={sr.stage_name} version={sr.output_version} /> : '—'}
              </span>
            </div>
            {sr.error && <p className="error">{sr.error}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function ResourceLink({ name, version }) {
  return (
    <Link to={`/resources/${name}?version=${version}`}>
      {name}:{version}
    </Link>
  )
}

function formatResources(versions) {
  const entries = Object.entries(versions || {})
  if (entries.length === 0) return '(none)'
  return entries.map(([name, version], i) => (
    <span key={name}>
      {i > 0 && ', '}
      <ResourceLink name={name} version={version} />
    </span>
  ))
}

function formatTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
