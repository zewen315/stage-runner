import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listPendingSchedules, listRuns, listWorkflows } from '../api.js'

const POLL_MS = 3000
const ONGOING_STATUSES = new Set(['requested', 'running'])
const FINISHED_LIMIT = 20

function byIdDesc(a, b) {
  return b.id - a.id
}

export default function Dashboard() {
  const [ongoing, setOngoing] = useState([])
  const [scheduled, setScheduled] = useState([])
  const [finished, setFinished] = useState([])
  const [error, setError] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    try {
      const workflows = await listWorkflows()
      const [runsByWorkflow, schedulesByWorkflow] = await Promise.all([
        Promise.all(workflows.map((name) => listRuns(name, FINISHED_LIMIT))),
        Promise.all(workflows.map((name) => listPendingSchedules(name))),
      ])

      const allRuns = runsByWorkflow.flat()

      setOngoing(allRuns.filter((r) => ONGOING_STATUSES.has(r.status)).sort(byIdDesc))
      setFinished(
        allRuns
          .filter((r) => !ONGOING_STATUSES.has(r.status))
          .sort(byIdDesc)
          .slice(0, FINISHED_LIMIT),
      )
      setScheduled(schedulesByWorkflow.flat().sort(byIdDesc))
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, POLL_MS)
    return () => clearInterval(interval)
  }, [load])

  if (error) return <p className="error">{error}</p>
  if (!loaded) return <p className="muted">Loading...</p>

  return (
    <div className="dashboard">
      <Column title="Ongoing" count={ongoing.length} accent="running">
        {ongoing.length === 0 ? (
          <EmptyState text="Nothing running right now." />
        ) : (
          ongoing.map((run) => <RunCard key={run.id} run={run} />)
        )}
      </Column>

      <Column title="Scheduled" count={scheduled.length} accent="requested">
        {scheduled.length === 0 ? (
          <EmptyState text="No runs waiting to start." />
        ) : (
          scheduled.map((s) => <ScheduleCard key={s.id} schedule={s} />)
        )}
      </Column>

      <Column title="Finished" count={finished.length} accent="completed">
        {finished.length === 0 ? (
          <EmptyState text="Nothing has finished yet." />
        ) : (
          finished.map((run) => <RunCard key={run.id} run={run} />)
        )}
      </Column>
    </div>
  )
}

function Column({ title, count, accent, children }) {
  return (
    <section className="column">
      <header className="column-header">
        <span className={`dot dot-${accent}`} />
        <h2>{title}</h2>
        <span className="column-count">{count}</span>
      </header>
      <div className="column-body">{children}</div>
    </section>
  )
}

function EmptyState({ text }) {
  return <p className="empty-state">{text}</p>
}

function RunCard({ run }) {
  return (
    <Link to={`/workflows/${run.workflow_name}/runs/${run.id}`} className={`run-card status-border-${run.status}`}>
      <div className="run-card-top">
        <span className="workflow-pill">{run.workflow_name}</span>
        <span className={`status status-${run.status}`}>{run.status}</span>
      </div>
      <div className="run-card-meta">
        <span>run #{run.id}</span>
        {run.start_from && <span>from {run.start_from}</span>}
        {run.stop_after && <span>to {run.stop_after}</span>}
      </div>
      <div className="run-card-time">{formatTime(run.requested_at)}</div>
    </Link>
  )
}

function ScheduleCard({ schedule }) {
  return (
    <div className="run-card status-border-requested">
      <div className="run-card-top">
        <span className="workflow-pill">{schedule.workflow_name}</span>
        <span className="status status-requested">waiting</span>
      </div>
      <div className="run-card-meta">
        <span>schedule #{schedule.id}</span>
        {schedule.start_from && <span>from {schedule.start_from}</span>}
        {schedule.stop_after && <span>to {schedule.stop_after}</span>}
      </div>
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
