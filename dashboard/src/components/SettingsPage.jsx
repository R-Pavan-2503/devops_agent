import { useEffect, useMemo, useState } from 'react'
import { Save, Coins, Bot } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

const PARAM_DESCRIPTIONS = {
  temperature:
    'Controls randomness. Lower values are more deterministic; higher values increase creativity and variability.',
  max_tokens:
    'Caps response length. Higher values allow longer outputs but consume more tokens and can increase latency.',
  top_p:
    'Nucleus sampling cutoff. Lower values focus on high-probability tokens; 1.0 considers the full distribution.',
  frequency_penalty:
    'Reduces repeated token frequency. Higher values discourage repeated words and phrases.',
  presence_penalty:
    'Encourages introducing new topics/tokens. Higher values push the model away from already used concepts.',
}

const FLOAT_RANGES = {
  temperature: { min: 0, max: 2, step: 0.01 },
  top_p: { min: 0, max: 1, step: 0.01 },
  frequency_penalty: { min: -2, max: 2, step: 0.01 },
  presence_penalty: { min: -2, max: 2, step: 0.01 },
}

function toNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : value
}

const SettingsPage = ({ onSaved }) => {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [availabilityError, setAvailabilityError] = useState('')
  const [agents, setAgents] = useState({})
  const [modelsBySize, setModelsBySize] = useState({ small: [], large: [] })
  const [usage, setUsage] = useState({ by_model: [], total: { tokens_used: 0, estimated_credits: 0 } })
  const [draftCustom, setDraftCustom] = useState({})

  const orderedAgentEntries = useMemo(
    () =>
      Object.entries(agents).sort((a, b) => {
        const aName = a[1]?.display_name || a[0]
        const bName = b[1]?.display_name || b[0]
        return aName.localeCompare(bName)
      }),
    [agents]
  )

  const loadUsage = async () => {
    try {
      const usageRes = await fetch(`${API_BASE}/api/settings/usage`)
      if (!usageRes.ok) return
      const usageData = await usageRes.json()
      setUsage(usageData)
    } catch {
      // best-effort polling
    }
  }

  useEffect(() => {
    let active = true
    const bootstrap = async () => {
      try {
        setError('')
        const [settingsRes, usageRes] = await Promise.all([
          fetch(`${API_BASE}/api/settings`),
          fetch(`${API_BASE}/api/settings/usage`),
        ])
        if (!settingsRes.ok) throw new Error('Failed to load settings')
        if (!usageRes.ok) throw new Error('Failed to load usage')

        const settingsData = await settingsRes.json()
        const usageData = await usageRes.json()
        if (!active) return
        setAgents(settingsData.current || {})
        setModelsBySize(settingsData.models_by_size || { small: [], large: [] })
        setAvailabilityError(settingsData.availability_error || '')
        setUsage(usageData)
      } catch (err) {
        if (!active) return
        setError(err.message || 'Unable to load settings')
      } finally {
        if (active) setLoading(false)
      }
    }

    bootstrap()
    const poll = setInterval(loadUsage, 5000)
    return () => {
      active = false
      clearInterval(poll)
    }
  }, [])

  const updateAgent = (agentKey, updater) => {
    setAgents((prev) => {
      const current = prev[agentKey]
      if (!current) return prev
      return { ...prev, [agentKey]: updater(current) }
    })
  }

  const updateModel = (agentKey, model) => {
    updateAgent(agentKey, (agent) => ({ ...agent, model }))
  }

  const updateParam = (agentKey, paramKey, value) => {
    updateAgent(agentKey, (agent) => ({
      ...agent,
      parameters: {
        ...(agent.parameters || {}),
        [paramKey]: value,
      },
    }))
  }

  const deleteParam = (agentKey, paramKey) => {
    updateAgent(agentKey, (agent) => {
      const next = { ...(agent.parameters || {}) }
      delete next[paramKey]
      return { ...agent, parameters: next }
    })
  }

  const addCustomParam = (agentKey) => {
    const draft = draftCustom[agentKey] || { key: '', value: '' }
    const key = draft.key.trim()
    if (!key) return
    updateParam(agentKey, key, toNumber(draft.value))
    setDraftCustom((prev) => ({ ...prev, [agentKey]: { key: '', value: '' } }))
  }

  const getModelOptions = (agent) => {
    const sizeClass = agent?.size_class || 'small'
    const options = [...(modelsBySize[sizeClass] || [])]
    if (agent?.model && !options.some((m) => m.id === agent.model)) {
      options.push({ id: agent.model, available: true, unavailable_reason: '' })
    }
    return options
  }

  const saveAll = async () => {
    try {
      setSaving(true)
      setError('')
      const res = await fetch(`${API_BASE}/api/settings/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agents }),
      })
      if (!res.ok) throw new Error('Failed to save settings')
      const data = await res.json()
      setAgents(data.current || agents)
      onSaved?.('Settings saved for this session')
    } catch (err) {
      setError(err.message || 'Unable to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="h-full w-full flex items-center justify-center text-gray-400">
        Loading settings...
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-background text-gray-200 p-6 space-y-6">
      <section className="border border-border rounded-lg bg-surface/60 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Coins className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold">API Credit Usage (Session)</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-gray-400">
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-4">Model</th>
                <th className="text-left py-2 pr-4">Tokens Used</th>
                <th className="text-left py-2">Estimated Credits</th>
              </tr>
            </thead>
            <tbody>
              {usage.by_model?.length ? (
                usage.by_model.map((row) => (
                  <tr key={row.model} className="border-b border-border/40">
                    <td className="py-2 pr-4 font-mono text-xs">{row.model}</td>
                    <td className="py-2 pr-4">{row.tokens_used}</td>
                    <td className="py-2">{row.estimated_credits}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="py-3 text-gray-500">
                    No usage recorded in this session yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-4 text-sm text-gray-300">
          Total: <span className="font-semibold">{usage.total?.tokens_used || 0}</span> tokens |{' '}
          <span className="font-semibold">{usage.total?.estimated_credits || 0}</span> credits
        </div>
      </section>

      {availabilityError && (
        <div className="text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 px-3 py-2 rounded-md">
          Model availability check: {availabilityError}
        </div>
      )}

      {error && (
        <div className="text-sm text-error bg-error/10 border border-error/30 px-3 py-2 rounded-md">{error}</div>
      )}

      {orderedAgentEntries.map(([agentKey, agent]) => {
        const params = agent.parameters || {}
        const modelOptions = getModelOptions(agent)
        const customDraft = draftCustom[agentKey] || { key: '', value: '' }

        return (
          <section key={agentKey} className="border border-border rounded-lg bg-surface/60 p-5">
            <div className="flex items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-secondary" />
                <div>
                  <h3 className="text-base font-semibold">{agent.display_name}</h3>
                  <p className="text-xs text-gray-400">Size class: {agent.size_class}</p>
                </div>
              </div>
              <div className="w-full max-w-md">
                <label className="text-xs text-gray-400 block mb-1">Model</label>
                <select
                  value={agent.model}
                  onChange={(e) => updateModel(agentKey, e.target.value)}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm"
                >
                  {modelOptions.map((option) => (
                    <option key={option.id} value={option.id} disabled={!option.available}>
                      {option.id}
                      {!option.available ? ' (Unavailable)' : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-4">
              {Object.entries(params).map(([paramKey, rawValue]) => {
                const isFloat = Object.prototype.hasOwnProperty.call(FLOAT_RANGES, paramKey)
                const isInt = paramKey === 'max_tokens'
                const description = PARAM_DESCRIPTIONS[paramKey] || 'Custom parameter passed to the model request.'
                const range = FLOAT_RANGES[paramKey]
                const value = isFloat || isInt ? Number(rawValue) || 0 : rawValue

                return (
                  <div key={paramKey} className="border border-border/70 rounded-md p-3 space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-xs text-primary">{paramKey}</span>
                      <button
                        type="button"
                        onClick={() => deleteParam(agentKey, paramKey)}
                        className="text-xs text-error hover:underline"
                      >
                        Delete
                      </button>
                    </div>

                    {isFloat && (
                      <div className="flex items-center gap-3">
                        <input
                          type="range"
                          min={range.min}
                          max={range.max}
                          step={range.step}
                          value={value}
                          onChange={(e) => updateParam(agentKey, paramKey, Number(e.target.value))}
                          className="w-full"
                        />
                        <input
                          type="number"
                          min={range.min}
                          max={range.max}
                          step={range.step}
                          value={value}
                          onChange={(e) => updateParam(agentKey, paramKey, Number(e.target.value))}
                          className="w-28 bg-background border border-border rounded-md px-2 py-1 text-sm"
                        />
                      </div>
                    )}

                    {isInt && (
                      <input
                        type="number"
                        step={1}
                        value={value}
                        onChange={(e) => updateParam(agentKey, paramKey, parseInt(e.target.value || '0', 10))}
                        className="w-40 bg-background border border-border rounded-md px-2 py-1 text-sm"
                      />
                    )}

                    {!isFloat && !isInt && (
                      <input
                        type="text"
                        value={String(rawValue ?? '')}
                        onChange={(e) => updateParam(agentKey, paramKey, e.target.value)}
                        className="w-full bg-background border border-border rounded-md px-2 py-1 text-sm"
                      />
                    )}

                    <p className="text-xs text-gray-400">{description}</p>
                    <p className="text-xs text-gray-300">
                      Current value: <span className="font-mono">{String(rawValue)}</span>
                    </p>
                  </div>
                )
              })}
            </div>

            <div className="mt-4 border-t border-border/60 pt-4">
              <p className="text-sm text-gray-300 mb-2">Add Custom Parameter</p>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                <input
                  type="text"
                  placeholder="parameter_key"
                  value={customDraft.key}
                  onChange={(e) =>
                    setDraftCustom((prev) => ({
                      ...prev,
                      [agentKey]: { ...customDraft, key: e.target.value },
                    }))
                  }
                  className="bg-background border border-border rounded-md px-2 py-2 text-sm"
                />
                <input
                  type="text"
                  placeholder="value"
                  value={customDraft.value}
                  onChange={(e) =>
                    setDraftCustom((prev) => ({
                      ...prev,
                      [agentKey]: { ...customDraft, value: e.target.value },
                    }))
                  }
                  className="bg-background border border-border rounded-md px-2 py-2 text-sm"
                />
                <button
                  type="button"
                  onClick={() => addCustomParam(agentKey)}
                  className="bg-primary/20 border border-primary/40 text-primary rounded-md px-3 py-2 text-sm hover:bg-primary/30"
                >
                  Add Parameter
                </button>
              </div>
            </div>
          </section>
        )
      })}

      <div className="sticky bottom-0 bg-background/90 backdrop-blur border-t border-border py-4">
        <button
          type="button"
          disabled={saving}
          onClick={saveAll}
          className="inline-flex items-center gap-2 bg-primary text-white px-5 py-2 rounded-md hover:bg-primary/90 disabled:opacity-60"
        >
          <Save className="w-4 h-4" />
          {saving ? 'Saving...' : 'Save'}
        </button>
        <span className="ml-3 text-xs text-gray-400">
          Save applies model + parameter changes to the current in-memory session only.
        </span>
      </div>
    </div>
  )
}

export default SettingsPage
