import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { cancelRecurringSchedule, listRecurringSchedules } from '../api.js'
import Modal from '../components/Modal.jsx'

export default function RecurringScheduleDetail() {
  const { name, recurringId } = useParams()
  const [recurring, setRecurring] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState(null)

  function load() {
    listRecurringSchedules(name)
      .then((rows) => {
        const found = rows.find((r) => String(r.id) === recurringId)
        if (found) setRecurring(found)
        else setNotFound(true)
      })
      .catch((e) => setError(e.message))
  }

  useEffect(load, [name, recurringId])

  async function handleCancel() {
    setConfirming(false)
    setCancelling(true)
    setCancelError(null)
    try {
      await cancelRecurringSchedule(name, recurringId)
      load()
    } catch (e) {
      setCancelError(e.message)
    } finally {
      setCancelling(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (notFound) return <p className="error">No recurring schedule {recurringId} for {name}.</p>
  if (!recurring) return <p className="muted">Loading...</p>

  const cadence = recurring.cron_expression != null ? recurring.cron_expression : `every ${recurring.interval_seconds}s`

  return (
    <div className="page-narrow">
      <p>
        <Link to="/" className="back-link">
          &larr; Dashboard
        </Link>
      </p>

      <div className="run-header">
        <div>
          <Link to={`/workflows/${recurring.workflow_name}`} className="workflow-pill">
            {recurring.workflow_name}
          </Link>
          <h1>Recurring schedule #{recurring.id}</h1>
        </div>
        <span className={`status status-lg status-${recurring.enabled ? 'requested' : 'cancelled'}`}>
          {recurring.enabled ? 'enabled' : 'cancelled'}
        </span>
      </div>

      <div className="card">
        <dl className="meta">
          <dt>Cadence</dt>
          <dd className="mono">{cadence}</dd>
          <dt>Start from</dt>
          <dd>{recurring.start_from || '(natural roots)'}</dd>
          <dt>Stop after</dt>
          <dd>{recurring.stop_after || '(run to completion)'}</dd>
          <dt>On failure</dt>
          <dd>{recurring.on_failure || '(workflow default)'}</dd>
          <dt>Next run</dt>
          <dd>{recurring.enabled ? formatTime(recurring.next_run_at) : '—'}</dd>
          <dt>Created</dt>
          <dd>{formatTime(recurring.created_at)}</dd>
        </dl>
        {cancelError && <p className="error run-error">{cancelError}</p>}

        {recurring.enabled && (
          <div className="row-actions row-actions-top">
            <button className="btn-danger" onClick={() => setConfirming(true)} disabled={cancelling}>
              {cancelling ? 'Cancelling...' : 'Cancel recurring schedule'}
            </button>
          </div>
        )}
      </div>

      {confirming && (
        <Modal onClose={() => setConfirming(false)}>
          <h2>Cancel recurring schedule #{recurring.id}?</h2>
          <div className="modal-body">
            <p>
              This stops <strong>{recurring.workflow_name}</strong> firing on this schedule
              ({cadence}) going forward. It doesn't affect runs already in progress or already
              finished.
            </p>
          </div>
          <div className="modal-actions">
            <button className="btn-ghost" onClick={() => setConfirming(false)}>
              Keep it
            </button>
            <button className="btn-danger" onClick={handleCancel}>
              Cancel recurring schedule
            </button>
          </div>
        </Modal>
      )}
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
