import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getResource, listStages, listVersions, listWorkflows, requestRun } from '../api.js'

const BEGINNING = ''

export default function NewRun() {
  const navigate = useNavigate()
  const [workflows, setWorkflows] = useState(null)
  const [workflowName, setWorkflowName] = useState('')
  const [loadError, setLoadError] = useState(null)

  const [stages, setStages] = useState([])
  const [startFrom, setStartFrom] = useState(BEGINNING)
  const [justThisStage, setJustThisStage] = useState(false)
  const [inputs, setInputs] = useState([]) // [{ key, versions: [numbers], value }]
  const [promote, setPromote] = useState(false)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

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
    setStartFrom(BEGINNING)
    setJustThisStage(false)
    setInputs([])
    listStages(workflowName)
      .then(setStages)
      .catch((e) => setFormError(e.message))
  }, [workflowName])

  async function handleStartFromChange(name) {
    setStartFrom(name)
    setJustThisStage(false)
    if (name === BEGINNING) {
      setInputs([])
      return
    }

    const stage = stages.find((s) => s.name === name)
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

    setSubmitting(true)
    try {
      await requestRun(workflowName, body)
      navigate('/')
    } catch (err) {
      setFormError(err.message)
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="error">{loadError}</p>
  if (workflows === null) return <p className="muted">Loading...</p>

  return (
    <div className="page-narrow">
      <h1>New run</h1>

      <form onSubmit={handleSubmit} className="card form">
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
          <select value={startFrom} onChange={(e) => handleStartFromChange(e.target.value)}>
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
              <input
                type="radio"
                checked={!justThisStage}
                onChange={() => setJustThisStage(false)}
              />
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

        {formError && <p className="error">{formError}</p>}

        <button type="submit" className="btn-primary" disabled={submitting || !workflowName}>
          {submitting ? 'Requesting...' : 'Trigger run'}
        </button>
      </form>
    </div>
  )
}
