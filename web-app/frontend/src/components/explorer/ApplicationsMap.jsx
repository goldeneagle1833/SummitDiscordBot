import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

export const STATUS_COLORS = {
  pending: '#fbbf24',
  pre_approved: '#60a5fa',
  approved: '#34d399',
  rejected: '#f87171',
}

// Roughly centred on North America, where most applications come from, but
// zoomed out far enough that overseas pins are still on screen.
const DEFAULT_CENTER = [39.5, -98.35]
const DEFAULT_ZOOM = 3

/**
 * Pin map of Explorer applications. Applications without coordinates are
 * simply not plotted — the review board lists them separately so an admin can
 * retry geocoding.
 */
export default function ApplicationsMap({ applications, onSelect }) {
  const pinned = applications.filter(
    (a) => typeof a.latitude === 'number' && typeof a.longitude === 'number'
  )

  return (
    // `isolate` gives the map its own stacking context. Leaflet puts z-index
    // 400-1000 on its panes and controls, and .leaflet-container creates no
    // stacking context of its own, so without this those values compete at the
    // page root and paint the map over dialogs.
    <div className="h-80 rounded-lg overflow-hidden border border-border isolate">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {pinned.map((application) => (
          <CircleMarker
            key={application.id}
            center={[application.latitude, application.longitude]}
            radius={8}
            pathOptions={{
              color: STATUS_COLORS[application.status] || STATUS_COLORS.pending,
              fillColor: STATUS_COLORS[application.status] || STATUS_COLORS.pending,
              fillOpacity: 0.7,
              weight: 2,
            }}
            eventHandlers={{ click: () => onSelect?.(application) }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-semibold">
                  {application.first_name} {application.last_name}
                </div>
                <div>{application.lgs_name}</div>
                <div>
                  {application.city}
                  {application.city && application.state ? ', ' : ''}
                  {application.state}
                </div>
                {application.average_score != null && (
                  <div>Avg score: {application.average_score}</div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
