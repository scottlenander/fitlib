// A map of one ride's route (ride page) or several overlaid (compare), drawn with Leaflet.
// On a plain background unless the street map is on: then OpenStreetMap's images go under
// it. Zwift routes are always on a plain background, as their positions aren't real places.
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import type { MapPoint } from '../api/client'
import { positionAt, stretch } from '../mapTrack'
import { useTheme } from '../theme'
import { seriesColours } from './Swatch'

// A route and which of the page's series colours it takes (its ride's place on compare).
export type MapRoute = { id: string; name: string; points: MapPoint[]; colour?: number }

type Props = {
  routes: MapRoute[]
  streetMap: boolean
  // What the map shows, for screen readers (the map itself is a picture).
  label: string
  // Ride page: the moment under the pointer in Ride Stats (seconds), and the stretch it's
  // zoomed to, both on the first route.
  cursorT?: number | null
  span?: [number, number] | null
  testId: string
}

const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

export function RouteMap({ routes, streetMap, label, cursorT = null, span = null, testId }: Props) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const drawn = useRef<L.LayerGroup | null>(null)
  const tiles = useRef<L.TileLayer | null>(null)
  const cursor = useRef<L.CircleMarker | null>(null)
  const highlight = useRef<L.Polyline | null>(null)
  const { theme } = useTheme()

  // The map itself, once.
  useEffect(() => {
    if (!element.current) return
    const instance = L.map(element.current, { zoomSnap: 0.25, scrollWheelZoom: false })
    instance.attributionControl.setPrefix(
      '<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">Leaflet</a>',
    )
    map.current = instance
    return () => {
      instance.remove()
      map.current = null
    }
  }, [])

  // OpenStreetMap's images under the routes, when chosen. Leaflet sends the page's origin as
  // the referrer for them only: OpenStreetMap asks web pages to say where they're from.
  useEffect(() => {
    const instance = map.current
    if (!instance) return
    if (streetMap) {
      tiles.current = L.tileLayer(TILES, {
        maxZoom: 19,
        attribution: OSM_CREDIT,
        referrerPolicy: 'strict-origin',
      }).addTo(instance)
    }
    return () => {
      tiles.current?.remove()
      tiles.current = null
    }
  }, [streetMap])

  // The routes, in the page's colours (redrawn when the theme changes them).
  useEffect(() => {
    const instance = map.current
    if (!instance) return
    const colours = seriesColours(Math.max(...routes.map((r, i) => (r.colour ?? i) + 1), 1))
    const group = L.layerGroup()
    const bounds = L.latLngBounds([])
    routes.forEach((route, i) => {
      const line = route.points.map((p) => [p.lat, p.lon] as [number, number])
      const first = line[0]
      const last = line[line.length - 1]
      if (!first || !last) return
      const colour = colours[route.colour ?? i] ?? colours[0] ?? 'blue'
      L.polyline(line, { color: colour, weight: 3, opacity: 0.85 })
        .bindTooltip(route.name, { sticky: true })
        .addTo(group)
      L.circleMarker(first, {
        radius: 6,
        color: colour,
        weight: 3,
        fillColor: '#ffffff',
        fillOpacity: 1,
      })
        .bindTooltip(`${route.name}: start`)
        .addTo(group)
      L.circleMarker(last, {
        radius: 6,
        color: colour,
        weight: 3,
        fillColor: colour,
        fillOpacity: 1,
      })
        .bindTooltip(`${route.name}: finish`)
        .addTo(group)
      bounds.extend(line)
    })
    group.addTo(instance)
    drawn.current = group
    if (bounds.isValid()) instance.fitBounds(bounds, { padding: [16, 16] })
    return () => {
      group.remove()
      drawn.current = null
    }
  }, [routes, theme])

  // The stretch Ride Stats is zoomed to, thicker on top.
  useEffect(() => {
    const instance = map.current
    const points = routes[0]?.points ?? []
    if (!instance || !span) return
    const colour = getComputedStyle(document.documentElement).getPropertyValue('--focus').trim()
    const line = L.polyline(stretch(points, span[0], span[1]), {
      color: colour || 'orange',
      weight: 6,
      opacity: 0.9,
      interactive: false,
    }).addTo(instance)
    highlight.current = line
    return () => {
      line.remove()
      highlight.current = null
    }
  }, [routes, span, theme])

  // Where the ride was at the moment under the pointer in Ride Stats.
  useEffect(() => {
    const instance = map.current
    const at = cursorT === null ? null : positionAt(routes[0]?.points ?? [], cursorT)
    if (!instance || !at) return
    const style = getComputedStyle(document.documentElement)
    const dot = L.circleMarker(at, {
      radius: 7,
      color: style.getPropertyValue('--text').trim() || '#000000',
      weight: 2,
      fillColor: style.getPropertyValue('--focus').trim() || 'orange',
      fillOpacity: 1,
      interactive: false,
    }).addTo(instance)
    cursor.current = dot
    return () => {
      dot.remove()
      cursor.current = null
    }
  }, [routes, cursorT])

  return (
    <div
      ref={element}
      className="route-map"
      role="region"
      aria-label={`${label}. Arrow keys move the map; plus and minus zoom.`}
      data-testid={testId}
      // What's drawn, for tests (the drawing itself is Leaflet's).
      data-routes={routes.filter((r) => r.points.length > 0).length}
      data-street-map={streetMap ? 'on' : 'off'}
      data-cursor={cursorT !== null && positionAt(routes[0]?.points ?? [], cursorT) ? 'on' : 'off'}
      data-span={span ? 'on' : 'off'}
    />
  )
}
