import { useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const CARTO = '&copy; <a href="https://carto.com/attributions">CARTO</a>'

/**
 * Basemaps that suit a dark site. All are free and need no API key.
 * Dark is the default because the plain OSM tiles glare against the theme.
 */
export const MAP_STYLES = {
  dark: {
    label: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: `${OSM} ${CARTO}`,
  },
  midnight: {
    label: 'Midnight',
    url: 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',
    attribution: `${OSM} ${CARTO}`,
  },
  voyager: {
    label: 'Voyager',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attribution: `${OSM} ${CARTO}`,
  },
  light: {
    label: 'Light',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: `${OSM} ${CARTO}`,
  },
}

export const DEFAULT_STYLE = 'dark'

// Roughly centred on North America, where most of the Series happens, but
// zoomed out far enough that overseas pins stay on screen.
const DEFAULT_CENTER = [39.5, -98.35]
const DEFAULT_ZOOM = 3

function readStoredStyle(storageKey) {
  if (!storageKey) return DEFAULT_STYLE
  try {
    const stored = localStorage.getItem(storageKey)
    return stored && MAP_STYLES[stored] ? stored : DEFAULT_STYLE
  } catch {
    return DEFAULT_STYLE
  }
}

/**
 * Shared pin map for the Explorer Series.
 *
 * `points` are already-geocoded items: { id, latitude, longitude, color,
 * title, lines[] }. Anything without coordinates should be filtered out by
 * the caller, which can then say so in its own words.
 */
export default function SeriesMap({
  points = [],
  onSelect,
  height = 'h-80',
  storageKey,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
}) {
  const [style, setStyle] = useState(() => readStoredStyle(storageKey))

  const pickStyle = (next) => {
    setStyle(next)
    if (!storageKey) return
    try {
      localStorage.setItem(storageKey, next)
    } catch {
      // A viewer with storage blocked just loses the preference.
    }
  }

  const tiles = MAP_STYLES[style] || MAP_STYLES[DEFAULT_STYLE]

  return (
    <div className="space-y-2">
      {/* `isolate` gives the map its own stacking context. Leaflet puts
          z-index 400-1000 on its panes and controls, and .leaflet-container
          creates no stacking context of its own, so without this those values
          compete at the page root and paint the map over dialogs. */}
      <div className={`${height} rounded-lg overflow-hidden border border-border isolate`}>
        <MapContainer
          center={center}
          zoom={zoom}
          scrollWheelZoom={false}
          style={{ height: '100%', width: '100%', background: 'transparent' }}
        >
          <TileLayer key={style} attribution={tiles.attribution} url={tiles.url} />
          {points.map((point) => (
            <CircleMarker
              key={point.id}
              center={[point.latitude, point.longitude]}
              radius={point.radius || 8}
              pathOptions={{
                color: point.color,
                fillColor: point.color,
                fillOpacity: 0.75,
                weight: 2,
              }}
              eventHandlers={onSelect ? { click: () => onSelect(point) } : undefined}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold">{point.title}</div>
                  {(point.lines || []).filter(Boolean).map((line) => (
                    <div key={line}>{line}</div>
                  ))}
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-text-muted mr-1">Map style</span>
        {Object.entries(MAP_STYLES).map(([key, option]) => (
          <button
            key={key}
            onClick={() => pickStyle(key)}
            aria-pressed={style === key}
            className={`text-xs px-2 py-0.5 rounded border transition-colors ${
              style === key
                ? 'border-secondary text-secondary'
                : 'border-border text-text-muted hover:border-secondary'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
