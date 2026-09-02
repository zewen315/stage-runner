import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { listRuns, listStages } from '../api.js'
import RunCard from '../components/RunCard.jsx'
import WorkflowGraph from '../components/WorkflowGraph.jsx'
import { depthLevels } from '../dagLayout.js'
import { useNewRunModal } from '../NewRunModalContext.jsx'

const RUNS_LIMIT = 20

export default function WorkflowDetail() {
  const { name } = useParams()
  const { open } = useNewRunModal()
  const [stages, setStages] = useState(null)
  const [runs, setRuns] = useState(null)
  const [error, setError] = useState(null)
  const [view, setView] = useState('graph') // 'graph' | 'list'

  useEffect(() => {
    let cancelled = false

    Promise.all([listStages(name), listRuns(name, RUNS_LIMIT)])
      .then(([stageList, runList]) => {
        if (cancelled) return
        setStages(stageList)
        setRuns(runList)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })

    return () => {
      cancelled = true
    }
  }, [name])

  if (error) return <p className="error">{error}</p>
  if (stages === null || runs === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-wide">
      <p>
        <Link to="/workflows" className="back-link">
          &larr; Workflows
        </Link>
      </p>

      <div className="run-header">
        <h1>{name}</h1>
        <button className="btn-primary" onClick={() => open({ workflow: name })}>
          + New run
        </button>
      </div>

      <h2>Structure</h2>
      <div className="view-toggle">
        <button
          className={`btn-ghost ${view === 'graph' ? 'active' : ''}`}
          onClick={() => setView('graph')}
        >
          Graph
        </button>
        <button className={`btn-ghost ${view === 'list' ? 'active' : ''}`} onClick={() => setView('list')}>
          List
        </button>
      </div>

      {view === 'graph' ? (
        <WorkflowGraph stages={stages} />
      ) : (
        <div className="stage-list">
          {depthLevels(stages).map((level, i) => (
            <div key={i} className="stage-row">
              {level.map((stage) => (
                <div key={stage.name} className="stage-card">
                  <div className="stage-card-top">
                    <span className="stage-name">{stage.name}</span>
                    {stage.retries > 0 && <span className="badge badge-attempts">retries: {stage.retries}</span>}
                  </div>
                  <div className="stage-card-meta">
                    <span>
                      depends on: {stage.depends_on.length === 0 ? '(nothing)' : stage.depends_on.join(', ')}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <h2>Recent runs</h2>
      {runs.length === 0 ? (
        <p className="muted">No runs yet.</p>
      ) : (
        <div className="run-card-grid">
          {runs.map((r) => (
            <RunCard key={r.id} run={r} showWorkflow={false} />
          ))}
        </div>
      )}
    </div>
  )
}
