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
  if (!run) return <p>Loading...</p>

  return (
    <div>
      <p>
        <Link to={`/workflows/${name}`}>&larr; {name}</Link>
      </p>
      <h1>
        Run #{run.id} <span className={`status status-${run.status}`}>{run.status}</span>
      </h1>
      <dl className="meta">
        <dt>Requested</dt>
        <dd>{run.requested_at}</dd>
        <dt>Started</dt>
        <dd>{run.started_at || '—'}</dd>
        <dt>Finished</dt>
        <dd>{run.finished_at || '—'}</dd>
        <dt>Start from</dt>
        <dd>{run.start_from || '(natural roots)'}</dd>
        <dt>Stop after</dt>
        <dd>{run.stop_after || '(run to completion)'}</dd>
        <dt>Promote</dt>
        <dd>{String(run.promote)}</dd>
      </dl>
      {run.error && <p className="error">{run.error}</p>}

      <h2>Stage runs</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Stage</th>
            <th>Status</th>
            <th>Input versions</th>
            <th>Output version</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {stageRuns.map((sr) => (
            <tr key={sr.id}>
              <td>{sr.stage_name}</td>
              <td>
                <span className={`status status-${sr.status}`}>{sr.status}</span>
              </td>
              <td>{JSON.stringify(sr.input_versions)}</td>
              <td>{sr.output_version ?? '—'}</td>
              <td className="error">{sr.error || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
