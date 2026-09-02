import { useEffect, useRef, useState } from 'react'
import { getResource, listStages, listVersions, listWorkflows, requestRun } from '../api.js'

const BEGINNING = ''

export default function NewRunForm({ initialWorkflow = '', initialStartFrom = '', onDone }) {
  const [workflows, setWorkflows] = useState(null)
  const [workflowName, setWorkflowName] = useState(initialWorkflow)
  const [loadError, setLoadError] = useState(null)

  const [stages, setStages] = useState([])
  const [startFrom, setStartFrom] = useState(BEGINNING)
  const [justThisStage, setJustThisStage] = useState(false)
  const [inputs, setInputs] = useState([]) // [{ key, versions: [numbers], value }]
  const [promote, setPromote] = useState(false)
  const [runAt, setRunAt] = useState('') // datetime-local string, browser-local time; '' = now
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const pendingInitialStartFrom = useRef(initialStartFrom)

  useEffect(() => {
    listWorkflows()
      .then((names) => {
        setWorkflows(names)
        setWorkflowName((current) => current || names[0] || '')
      })
      .catch((e) => setLoadError(e.message))
  }, [])

  useEffect(() => {
    if (!workflowName) return
    listStages(workflowName)
      .then((stageList) => {
        setStages(stageList)
        const toApply = pendingInitialStartFrom.current
        pendingInitialStartFrom.current = null
        if (toApply && stageList.some((s) => s.name === toApply)) {
          applyStartFrom(toApply, stageList)
        } else {
          setStartFrom(BEGINNING)
          setJustThisStage(false)
          setInputs([])
        }
      })
      .catch((e) => setFormError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowName])

  async function applyStartFrom(name, stageList) {
    setStartFrom(name)
    setJustThisStage(false)
    if (name === BEGINNING) {
      setInputs([])
      return
    }

    const stage = stageList.find((s) => s.name === name)
    const deps = stage?.depends_on || []
    setInputs(deps.map((dep) => ({ key: dep, versions: [], value: '' })))

    const rows = await Promise.all(
      deps.map(async (dep) => {
        const [versions, current] = await Promise.all([
          listVersions(dep).catch(() => []),
          getResource(dep)
            .then((snapshot) => snapshot.version.version)
            .catch(() => null),
        ])
        const numbers = versions.map((v) => v.version)
        const defaultValue = current ?? numbers[numbers.length - 1] ?? ''
        return { key: dep, versions: numbers, value: defaultValue === '' ? '' : String(defaultValue) }
      }),
    )
    setInputs(rows)
  }

  function updateInputValue(index, value) {
    setInputs((prev) => prev.map((row, i) => (i === index ? { ...row, value } : row)))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError(null)

    if (!workflowName) {
      setFormError('Choose a workflow.')
      return
    }

    const body = {}
    if (startFrom !== BEGINNING) {
      body.start_from = startFrom
      if (justThisStage) body.stop_after = startFrom

      const inputVersions = {}
      for (const { key, value } of inputs) {
        const parsed = Number(value)
        if (value === '' || !Number.isInteger(parsed)) {
          setFormError(`Choose a version for "${key}" -- ${startFrom} depends on it directly.`)
          return
        }
        inputVersions[key] = parsed
      }
      body.input_versions = inputVersions
    }
    if (promote) body.promote = true
    if (runAt) body.run_at = new Date(runAt).toISOString()

    setSubmitting(true)
    try {
      await requestRun(workflowName, body)
      onDone()
    } catch (err) {
      setFormError(err.message)
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="error">{loadError}</p>
  if (workflows === null) return <p className="muted">Loading...</p>

  return (
    <>
      <h2>New run</h2>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Workflow
          <select value={workflowName} onChange={(e) => setWorkflowName(e.target.value)}>
            {workflows.length === 0 && <option value="">No workflows found</option>}
            {workflows.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Start from
          <select value={startFrom} onChange={(e) => applyStartFrom(e.target.value, stages)}>
            <option value={BEGINNING}>(Beginning)</option>
            {stages.map((stage) => (
              <option key={stage.name} value={stage.name}>
                {stage.name}
              </option>
            ))}
          </select>
        </label>

        {startFrom !== BEGINNING && (
          <div className="radio-group">
            <label className="radio-option">
              <input type="radio" checked={!justThisStage} onChange={() => setJustThisStage(false)} />
              Run to the end
            </label>
            <label className="radio-option">
              <input type="radio" checked={justThisStage} onChange={() => setJustThisStage(true)} />
              Just this stage
            </label>
          </div>
        )}

        {startFrom !== BEGINNING && (
          <fieldset>
            <legend>Input versions</legend>
            <p className="hint">
              {inputs.length === 0
                ? `${startFrom} has no dependencies of its own.`
                : `${startFrom} depends on these directly -- pick which version of each to use.`}
            </p>
            {inputs.map((row, i) => (
              <div key={row.key} className="input-row">
                <span className="input-row-label">{row.key}</span>
                <select value={row.value} onChange={(e) => updateInputValue(i, e.target.value)}>
                  {row.versions.length === 0 && <option value="">no versions yet</option>}
                  {[...row.versions].reverse().map((v) => (
                    <option key={v} value={v}>
                      v{v}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </fieldset>
        )}

        <label className="checkbox">
          <input type="checkbox" checked={promote} onChange={(e) => setPromote(e.target.checked)} />
          Promote produced versions to current
        </label>

        <label>
          Run at <span className="hint-inline">(optional -- leave blank to run now)</span>
          <input type="datetime-local" value={runAt} onChange={(e) => setRunAt(e.target.value)} />
        </label>

        {formError && <p className="error">{formError}</p>}

        <div className="modal-actions">
          <button type="button" className="btn-ghost" onClick={onDone}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting || !workflowName}>
            {submitting ? 'Requesting...' : runAt ? 'Schedule run' : 'Trigger run'}
          </button>
        </div>
      </form>
    </>
  )
}
