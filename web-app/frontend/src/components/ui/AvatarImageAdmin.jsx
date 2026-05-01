import { useState, useCallback } from 'react'
import { updateAvatarImageSettings, resetAvatarImageSettings } from '@/api/admin'

const DEFAULTS = { brightness: 1.0, position_x: 50, position_y: 25, opacity: 0.5 }

export default function AvatarImageAdmin({ avatarName, imgSrc, currentSettings, onSaved }) {
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState(() => ({
    ...DEFAULTS,
    ...currentSettings,
  }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = useCallback((key, val) => {
    setSettings((prev) => ({ ...prev, [key]: val }))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await updateAvatarImageSettings(avatarName, settings)
      onSaved?.(avatarName, settings)
      setOpen(false)
    } catch (err) {
      setError(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    setError('')
    try {
      await resetAvatarImageSettings(avatarName)
      setSettings({ ...DEFAULTS })
      onSaved?.(avatarName, null)
      setOpen(false)
    } catch (err) {
      setError(err.message || 'Failed to reset')
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-text-muted hover:text-secondary transition-colors"
        title="Adjust image display"
      >
        Adjust Image
      </button>
    )
  }

  const previewStyle = {
    backgroundImage: imgSrc ? `url('${imgSrc}')` : undefined,
    backgroundSize: 'cover',
    backgroundPosition: `${settings.position_x}% ${settings.position_y}%`,
    filter: `brightness(${settings.brightness})`,
    opacity: settings.opacity,
  }

  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-4 mt-2 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-secondary">Image Settings — {avatarName}</h4>
        <button onClick={() => setOpen(false)} className="text-text-muted hover:text-text-primary text-sm">Close</button>
      </div>

      {/* Preview */}
      {imgSrc && (
        <div className="flex gap-3 items-start">
          {/* Card-style preview */}
          <div className="relative w-32 h-24 rounded overflow-hidden border border-border bg-bg-surface flex-shrink-0">
            <div className="absolute inset-0" style={previewStyle} />
            <div className="relative p-2 text-xs text-text-muted">Card Preview</div>
          </div>
          {/* Thumbnail preview */}
          <div className="w-16 h-16 rounded overflow-hidden border border-border flex-shrink-0">
            <img
              src={imgSrc}
              alt={avatarName}
              className="w-full h-full object-cover"
              style={{
                objectPosition: `${settings.position_x}% ${settings.position_y}%`,
                filter: `brightness(${settings.brightness})`,
              }}
            />
          </div>
        </div>
      )}

      {/* Opacity slider */}
      <div>
        <label className="text-xs text-text-muted flex justify-between">
          <span>Opacity</span>
          <span className="text-text-primary">{Math.round(settings.opacity * 100)}%</span>
        </label>
        <input
          type="range"
          min="0.0"
          max="1.0"
          step="0.05"
          value={settings.opacity}
          onChange={(e) => set('opacity', parseFloat(e.target.value))}
          className="w-full accent-secondary"
        />
      </div>

      {/* Brightness slider */}
      <div>
        <label className="text-xs text-text-muted flex justify-between">
          <span>Brightness</span>
          <span className="text-text-primary">{settings.brightness.toFixed(2)}</span>
        </label>
        <input
          type="range"
          min="0.1"
          max="2.0"
          step="0.05"
          value={settings.brightness}
          onChange={(e) => set('brightness', parseFloat(e.target.value))}
          className="w-full accent-secondary"
        />
      </div>

      {/* Position X slider */}
      <div>
        <label className="text-xs text-text-muted flex justify-between">
          <span>Horizontal Position</span>
          <span className="text-text-primary">{settings.position_x}%</span>
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={settings.position_x}
          onChange={(e) => set('position_x', parseInt(e.target.value))}
          className="w-full accent-secondary"
        />
      </div>

      {/* Position Y slider */}
      <div>
        <label className="text-xs text-text-muted flex justify-between">
          <span>Vertical Position</span>
          <span className="text-text-primary">{settings.position_y}%</span>
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={settings.position_y}
          onChange={(e) => set('position_y', parseInt(e.target.value))}
          className="w-full accent-secondary"
        />
      </div>

      {error && <p className="text-accent-red text-xs">{error}</p>}

      <div className="flex justify-between items-center">
        <button
          onClick={handleReset}
          disabled={saving}
          className="text-xs text-text-muted hover:text-accent-red disabled:opacity-50"
        >
          Reset to Default
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="text-xs bg-secondary text-bg-base px-4 py-1.5 rounded hover:opacity-90 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save for Everyone'}
        </button>
      </div>
    </div>
  )
}
