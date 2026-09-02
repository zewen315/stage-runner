import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { cancelSchedule, getSchedule } from '../api.js'

export default function ScheduleDetail() {
  const { name, scheduleId } = useParams()
  const [schedule, setSchedule] = useState(null)
  const [error, setError] = useState(null)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState(null)

  function load() {
    getSchedule(name, scheduleId)
      .then(setSchedule)
      .catch((e) => setError(e.message))
  }

  useEffect(load, [name, scheduleId])

  async function handleCancel() {
    setCancelling(true)
    setCancelError(null)
    try {
      await cancelSchedule(name, scheduleId)
      load()
    } catch (e) {
      setCancelError(e.message)
    } finally {
      setCancelling(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!schedule) return <p className="muted">Loading...</p>

  return (
    <div className="page-narrow">
      <p>
        <Link to="/" className="back-link">
          &larr; Dashboard
        </Link>
      </p>

      <div className="run-header">
        <div>
          <Link to={`/workflows/${schedule.workflow_name}`} className="workflow-pill">
            {schedule.workflow_name}
          </Link>
          <h1>Schedule #{schedule.id}</h1>
        </div>
        <span className={`status status-lg status-${schedule.status}`}>{schedule.status}</span>
      </div>

      <div className="card">
        <dl className="meta">
          <dt>Start from</dt>
          <dd>{schedule.start_from || '(natural roots)'}</dd>
          <dt>Stop after</dt>
          <dd>{schedule.stop_after || '(run to completion)'}</dd>
          <dt>Run at</dt>
          <dd>{schedule.run_at ? formatTime(schedule.run_at) : '(as soon as seen)'}</dd>
        </dl>
        {schedule.error && <p className="error run-error">{schedule.error}</p>}
        {cancelError && <p className="error run-error">{cancelError}</p>}

        <div className="row-actions row-actions-top">
          {schedule.run_id != null && (
            <Link to={`/workflows/${name}/runs/${schedule.run_id}`} className="btn-ghost">
              View run
            </Link>
          )}
          {schedule.run_id == null && schedule.status === 'requested' && (
            <button className="btn-ghost" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling...' : 'Cancel schedule'}
            </button>
          )}
        </div>
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
