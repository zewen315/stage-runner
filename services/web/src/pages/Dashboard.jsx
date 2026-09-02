import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listPendingSchedules, listRecurringSchedules, listRuns, listWorkflows } from '../api.js'
import Pagination, { paginate } from '../components/Pagination.jsx'
import RunCard from '../components/RunCard.jsx'

const POLL_MS = 3000
const PAGE_SIZE = 10
// Per-workflow fetch depth for runs -- deeper than PAGE_SIZE since it
// covers both the Ongoing and Finished columns at once, combined across
// every workflow, and Finished now paginates instead of hard-capping at
// one page's worth.
const RUN_FETCH_LIMIT = 50
const ONGOING_STATUSES = new Set(['requested', 'running'])

function byIdDesc(a, b) {
  return b.id - a.id
}

export default function Dashboard() {
  const [ongoing, setOngoing] = useState([])
  const [scheduled, setScheduled] = useState([])
  const [finished, setFinished] = useState([])
  const [error, setError] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const [scheduledPage, setScheduledPage] = useState(1)
  const [ongoingPage, setOngoingPage] = useState(1)
  const [finishedPage, setFinishedPage] = useState(1)

  const load = useCallback(async () => {
    try {
      const workflows = await listWorkflows()
      const [runsByWorkflow, pendingByWorkflow, recurringByWorkflow] = await Promise.all([
        Promise.all(workflows.map((name) => listRuns(name, RUN_FETCH_LIMIT))),
        Promise.all(workflows.map((name) => listPendingSchedules(name))),
        Promise.all(workflows.map((name) => listRecurringSchedules(name))),
      ])

      const allRuns = runsByWorkflow.flat()

      setOngoing(allRuns.filter((r) => ONGOING_STATUSES.has(r.status)).sort(byIdDesc))
      setFinished(allRuns.filter((r) => !ONGOING_STATUSES.has(r.status)).sort(byIdDesc))

      const pending = pendingByWorkflow.flat().sort(byIdDesc)
      const recurring = recurringByWorkflow
        .flat()
        .filter((r) => r.enabled)
        .sort((a, b) => a.next_run_at.localeCompare(b.next_run_at))
      setScheduled([...pending, ...recurring])
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

  const scheduledView = paginate(scheduled, scheduledPage, PAGE_SIZE)
  const ongoingView = paginate(ongoing, ongoingPage, PAGE_SIZE)
  const finishedView = paginate(finished, finishedPage, PAGE_SIZE)

  return (
    <div className="dashboard">
      <Column title="Scheduled" count={scheduled.length} accent="requested">
        {scheduled.length === 0 ? (
          <EmptyState text="No runs waiting to start." />
        ) : (
          <>
            <Pagination page={scheduledView.page} totalPages={scheduledView.totalPages} onChange={setScheduledPage} />
            {scheduledView.items.map((item) =>
              // Recurring schedules always carry next_run_at; one-time
              // schedules never do. cron_expression alone doesn't work as
              // the discriminator -- it's null for an interval-based
              // recurring schedule too, which would otherwise misrender it
              // as (and link it to) an unrelated one-time schedule.
              item.next_run_at != null ? (
                <RecurringScheduleCard key={`recurring-${item.id}`} schedule={item} />
              ) : (
                <ScheduleCard key={`once-${item.id}`} schedule={item} />
              ),
            )}
          </>
        )}
      </Column>

      <Column title="Ongoing" count={ongoing.length} accent="running">
        {ongoing.length === 0 ? (
          <EmptyState text="Nothing running right now." />
        ) : (
          <>
            <Pagination page={ongoingView.page} totalPages={ongoingView.totalPages} onChange={setOngoingPage} />
            {ongoingView.items.map((run) => (
              <RunCard key={run.id} run={run} />
            ))}
          </>
        )}
      </Column>

      <Column title="Finished" count={finished.length} accent="completed">
        {finished.length === 0 ? (
          <EmptyState text="Nothing has finished yet." />
        ) : (
          <>
            <Pagination page={finishedView.page} totalPages={finishedView.totalPages} onChange={setFinishedPage} />
            {finishedView.items.map((run) => (
              <RunCard key={run.id} run={run} />
            ))}
          </>
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

function ScheduleCard({ schedule }) {
  return (
    <Link
      to={`/workflows/${schedule.workflow_name}/schedules/${schedule.id}`}
      className="run-card status-border-requested"
    >
      <div className="run-card-top">
        <span className="workflow-pill">{schedule.workflow_name}</span>
        <span className="status status-requested">{schedule.run_at ? 'scheduled' : 'waiting'}</span>
      </div>
      <div className="run-card-meta">
        <span>schedule #{schedule.id}</span>
        {schedule.start_from && <span>from {schedule.start_from}</span>}
        {schedule.stop_after && <span>to {schedule.stop_after}</span>}
      </div>
      {schedule.run_at && <div className="run-card-time">at {formatTime(schedule.run_at)}</div>}
    </Link>
  )
}

function RecurringScheduleCard({ schedule }) {
  return (
    <Link
      to={`/workflows/${schedule.workflow_name}/recurring-schedules/${schedule.id}`}
      className="run-card status-border-requested"
    >
      <div className="run-card-top">
        <span className="workflow-pill">{schedule.workflow_name}</span>
        <span className="status status-requested">recurring</span>
      </div>
      <div className="run-card-meta">
        <span className="mono">
          {schedule.cron_expression != null ? schedule.cron_expression : `every ${schedule.interval_seconds}s`}
        </span>
        {schedule.start_from && <span>from {schedule.start_from}</span>}
        {schedule.stop_after && <span>to {schedule.stop_after}</span>}
      </div>
      <div className="run-card-time">next at {formatTime(schedule.next_run_at)}</div>
    </Link>
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
