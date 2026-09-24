import { useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const ESRI_ATTRIBUTION = 'Tiles &copy; <a href="https://www.esri.com">Esri</a>'
const esriTiles = (service) => `${ESRI}/${service}/MapServer/tile/{z}/{y}/{x}`

/**
 * Basemaps that suit a dark site, from Esri's public tile services, which
 * need no API key. (CARTO's basemaps, used before, started requiring one and
 * served an "API KEY REQUIRED" placeholder in place of every tile.)
 *
 * The Canvas styles ship their place names as a separate transparent layer,
 * drawn over the base as `labels`.
 */
export const MAP_STYLES = {
  dark: {
    label: 'Dark',
    url: esriTiles('Canvas/World_Dark_Gray_Base'),
    labels: esriTiles('Canvas/World_Dark_Gray_Reference'),
    attribution: `${ESRI_ATTRIBUTION} &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors`,
    maxZoom: 16,
  },
  midnight: {
    label: 'Midnight',
    url: esriTiles('Canvas/World_Dark_Gray_Base'),
    attribution: `${ESRI_ATTRIBUTION} &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors`,
    maxZoom: 16,
  },
  street: {
    label: 'Street',
    url: esriTiles('World_Street_Map'),
    attribution: `${ESRI_ATTRIBUTION} &mdash; Esri, HERE, Garmin, USGS, &copy; OpenStreetMap contributors`,
    maxZoom: 19,
  },
  light: {
    label: 'Light',
    url: esriTiles('Canvas/World_Light_Gray_Base'),
    labels: esriTiles('Canvas/World_Light_Gray_Reference'),
    attribution: `${ESRI_ATTRIBUTION} &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors`,
    maxZoom: 16,
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
          <TileLayer
            key={style}
            attribution={tiles.attribution}
            url={tiles.url}
            maxZoom={tiles.maxZoom}
          />
          {tiles.labels && (
            <TileLayer key={`${style}-labels`} url={tiles.labels} maxZoom={tiles.maxZoom} />
          )}
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
