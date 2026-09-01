import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { listRuns, requestRun } from '../api.js'

export default function WorkflowDetail() {
  const { name } = useParams()
  const [runs, setRuns] = useState(null)
  const [loadError, setLoadError] = useState(null)

  const [stage, setStage] = useState('')
  const [startFrom, setStartFrom] = useState('')
  const [stopAfter, setStopAfter] = useState('')
  const [inputs, setInputs] = useState([{ key: '', value: '' }])
  const [promote, setPromote] = useState(false)
  const [formError, setFormError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function loadRuns() {
    listRuns(name).then(setRuns).catch((e) => setLoadError(e.message))
  }

  useEffect(loadRuns, [name])

  function updateInput(index, field, value) {
    setInputs((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  function addInputRow() {
    setInputs((prev) => [...prev, { key: '', value: '' }])
  }

  function removeInputRow(index) {
    setInputs((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError(null)
    setNotice(null)

    if (stage && (startFrom || stopAfter)) {
      setFormError('Stage cannot be combined with start-from/stop-after -- use one or the other.')
      return
    }

    const body = {}
    const resolvedStartFrom = stage || startFrom || null
    const resolvedStopAfter = stage || stopAfter || null
    if (resolvedStartFrom) body.start_from = resolvedStartFrom
    if (resolvedStopAfter) body.stop_after = resolvedStopAfter

    const inputVersions = {}
    for (const { key, value } of inputs) {
      if (key.trim() === '') continue
      const parsed = Number(value)
      if (!Number.isInteger(parsed)) {
        setFormError(`Input "${key}" needs an integer version.`)
        return
      }
      inputVersions[key.trim()] = parsed
    }
    if (Object.keys(inputVersions).length > 0) body.input_versions = inputVersions
    if (promote) body.promote = true

    setSubmitting(true)
    try {
      const schedule = await requestRun(name, body)
      setNotice(`Requested (schedule #${schedule.id}). New runs appear below once dispatched.`)
      loadRuns()
      setTimeout(loadRuns, 3000)
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1>{name}</h1>

      <section>
        <h2>Trigger a run</h2>
        <form onSubmit={handleSubmit} className="trigger-form">
          <label>
            Stage (single-stage run)
            <input value={stage} onChange={(e) => setStage(e.target.value)} placeholder="e.g. score_items" />
          </label>
          <label>
            Start from
            <input value={startFrom} onChange={(e) => setStartFrom(e.target.value)} disabled={!!stage} />
          </label>
          <label>
            Stop after
            <input value={stopAfter} onChange={(e) => setStopAfter(e.target.value)} disabled={!!stage} />
          </label>

          <fieldset>
            <legend>Input versions</legend>
            <p className="hint">Pins for dependencies this run's start stage won't produce itself.</p>
            {inputs.map((row, i) => (
              <div key={i} className="input-row">
                <input
                  placeholder="resource name"
                  value={row.key}
                  onChange={(e) => updateInput(i, 'key', e.target.value)}
                />
                <input
                  placeholder="version"
                  value={row.value}
                  onChange={(e) => updateInput(i, 'value', e.target.value)}
                />
                <button type="button" onClick={() => removeInputRow(i)}>
                  Remove
                </button>
              </div>
            ))}
            <button type="button" onClick={addInputRow}>
              + Add input
            </button>
          </fieldset>

          <label className="checkbox">
            <input type="checkbox" checked={promote} onChange={(e) => setPromote(e.target.checked)} />
            Promote produced versions to current
          </label>

          {formError && <p className="error">{formError}</p>}
          {notice && <p>{notice}</p>}

          <button type="submit" disabled={submitting}>
            {submitting ? 'Requesting...' : 'Trigger run'}
          </button>
        </form>
      </section>

      <section>
        <h2>Recent runs</h2>
        {loadError && <p className="error">{loadError}</p>}
        {runs === null ? (
          <p>Loading...</p>
        ) : runs.length === 0 ? (
          <p>No runs yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Requested</th>
                <th>Start from</th>
                <th>Stop after</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link to={`/workflows/${name}/runs/${run.id}`}>{run.id}</Link>
                  </td>
                  <td>
                    <span className={`status status-${run.status}`}>{run.status}</span>
                  </td>
                  <td>{run.requested_at}</td>
                  <td>{run.start_from || '—'}</td>
                  <td>{run.stop_after || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
