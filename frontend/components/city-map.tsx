"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import L from "leaflet"
import { Crosshair, Layers3, Minus, Plus } from "lucide-react"
import type { Feature, FeatureCollection } from "geojson"
import type { Location } from "../lib/api"
import { heatColor, heatThresholds, numeric, temperature } from "../lib/format"

export type TileSelection = { temperature: number | null; sourceId: string | null; name?: string }

type MapProps = {
  heat?: FeatureCollection
  trees?: FeatureCollection
  context?: FeatureCollection
  locations: Location[]
  selectedId: string | null
  plannedIds: string[]
  hotspotThreshold?: number | null
  onSelectLocation: (id: string) => void
  onSelectTile: (tile: TileSelection) => void
}

const cityCenter: L.LatLngExpression = [37.991, 23.731]
const cityZoom = 12
const markerPin = '<svg width="23" height="27" viewBox="0 0 23 27" fill="none" aria-hidden="true"><path d="M11.5 1.2a9.7 9.7 0 0 0-9.7 9.7c0 6.7 9.7 14.7 9.7 14.7s9.7-8 9.7-14.7a9.7 9.7 0 0 0-9.7-9.7Z" stroke="white" stroke-width="2"/><circle cx="11.5" cy="10.9" r="3" fill="white"/></svg>'

function temperatureOf(feature?: Feature) {
  const number = feature?.properties?.temperature_c
  return typeof number === "number" && Number.isFinite(number) ? number : null
}

function asText(value: unknown) {
  return typeof value === "string" ? value : null
}

function tooltip(label: string) {
  const content = document.createElement("span")
  content.textContent = label
  return content
}

export default function CityMap({ heat, trees, context, locations, selectedId, plannedIds, hotspotThreshold, onSelectLocation, onSelectTile }: MapProps) {
  const container = useRef<HTMLDivElement | null>(null)
  const instance = useRef<L.Map | null>(null)
  const areaBounds = useRef<L.LatLngBounds | null>(null)
  const [showHeat, setShowHeat] = useState(true)
  const [showCanopy, setShowCanopy] = useState(false)
  const [showPlantings, setShowPlantings] = useState(false)
  const [showSchools, setShowSchools] = useState(false)
  const [showLayers, setShowLayers] = useState(false)
  const [tilesAvailable, setTilesAvailable] = useState(true)
  const [scale, setScale] = useState({ label: "1 km", width: 95 })
  const breaks = useMemo(() => heatThresholds(heat?.features.flatMap((feature) => temperatureOf(feature) ?? []) ?? [], hotspotThreshold), [heat, hotspotThreshold])

  useEffect(() => {
    if (!container.current) return
    const map = L.map(container.current, {
      zoomControl: false,
      scrollWheelZoom: false,
      minZoom: 10,
      maxZoom: 18,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      attributionControl: true,
    }).setView(cityCenter, cityZoom)
    instance.current = map
    map.attributionControl.setPrefix(false)
    for (const [name, zIndex] of [["heat", 380], ["context", 410], ["trees", 420]] as const) {
      map.createPane(name).style.zIndex = String(zIndex)
    }
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      className: "city-basemap",
      maxNativeZoom: 19,
      attribution: '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>',
    })
    let loadedTiles = 0
    tiles.on("tileload", () => { loadedTiles += 1; setTilesAvailable(true) })
    tiles.on("tileerror", () => { if (loadedTiles === 0) setTilesAvailable(false) })
    tiles.addTo(map)
    const updateScale = () => {
      const width = 120
      const distance = map.distance(map.containerPointToLatLng([0, 0]), map.containerPointToLatLng([width, 0]))
      if (!(distance > 0)) return
      const unit = 10 ** Math.floor(Math.log10(distance))
      const rounded = ([5, 3, 2, 1].find((value) => value * unit <= distance) ?? 1) * unit
      setScale({ label: rounded >= 1000 ? `${rounded / 1000} km` : `${rounded} m`, width: Math.round(rounded / distance * width) })
    }
    updateScale()
    map.on("zoomend", updateScale)
    const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resize.observe(container.current)
    return () => {
      resize.disconnect()
      map.remove()
      instance.current = null
      areaBounds.current = null
    }
  }, [])

  useEffect(() => {
    const map = instance.current
    if (!map || !context) return
    const shapes = L.geoJSON(context, {
      pane: "context",
      interactive: false,
      filter: (feature) => !!feature.geometry && (feature.properties?.kind !== "school" || showSchools),
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
        pane: "context", radius: 2.3, color: "#536080", weight: 1, fillColor: "#c2cce6", fillOpacity: 0.9, interactive: false,
      }),
      style: (feature) => {
        if (feature?.properties?.kind === "school") return { color: "#536080", weight: 1, fillColor: "#c2cce6", fillOpacity: 0.9 }
        const boundary = ["boundary", "district"].includes(String(feature?.properties?.kind)) || feature?.properties?.boundary
        const green = ["park", "green", "green_space"].includes(String(feature?.properties?.kind))
          || ["park", "garden"].includes(String(feature?.properties?.leisure))
        return {
          color: boundary ? "#514a57" : green ? "#8eb4a2" : "#c4cbd0",
          opacity: boundary ? 0.42 : 0.85,
          weight: boundary ? 1.2 : 1,
          dashArray: boundary ? "5 3" : undefined,
          fill: green,
          fillColor: "#9ed1a8",
          fillOpacity: 0.5,
        }
      },
    }).addTo(map)
    const bounds = shapes.getBounds()
    if (bounds.isValid() && !areaBounds.current) {
      areaBounds.current = bounds
      map.fitBounds(bounds, { maxZoom: 14, padding: [22, 38] })
    }
    return () => { shapes.remove() }
  }, [context, showSchools])

  useEffect(() => {
    const map = instance.current
    if (!map || !heat || !showHeat) return
    const layer = L.geoJSON(heat, {
      pane: "heat",
      style: (feature) => ({
        color: "#fff7e9",
        weight: 0.45,
        opacity: 0.53,
        fillColor: heatColor(temperatureOf(feature), breaks),
        fillOpacity: 0.68,
      }),
      onEachFeature: (feature, shape) => {
        const value = temperatureOf(feature)
        const selection = {
          temperature: value,
          sourceId: asText(feature.properties?.source_id),
          name: asText(feature.properties?.name) ?? undefined,
        }
        shape.on("click", () => onSelectTile(selection))
        if (value !== null) shape.bindTooltip(tooltip(temperature(value)), { sticky: true, direction: "top" })
      },
    }).addTo(map)
    return () => { layer.remove() }
  }, [breaks, heat, onSelectTile, showHeat])

  useEffect(() => {
    const map = instance.current
    if (!map || !trees || !(showCanopy || showPlantings)) return
    const renderer = L.canvas({ pane: "trees" })
    const layer = L.geoJSON(trees, {
      pane: "trees",
      interactive: false,
      filter: (feature) => !!feature.geometry && (feature.geometry.type === "Point" ? showPlantings : showCanopy),
      style: { renderer, color: "#217258", weight: 0.6, fillColor: "#46a973", fillOpacity: 0.4 },
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
        pane: "trees",
        renderer,
        radius: 1.5,
        color: "#1c624d",
        fillColor: "#419960",
        fillOpacity: 0.7,
        weight: 0.5,
        interactive: false,
      }),
    }).addTo(map)
    return () => { layer.remove(); renderer.remove() }
  }, [trees, showCanopy, showPlantings])

  useEffect(() => {
    const map = instance.current
    if (!map) return
    const markers = L.layerGroup().addTo(map)
    for (const location of locations) {
      const planned = plannedIds.includes(location.id)
      const selected = location.id === selectedId
      const priority = location.priority_band === "high"
      const icon = L.divIcon({
        html: markerPin,
        iconSize: [23, 27],
        iconAnchor: [11, 26],
        tooltipAnchor: [0, -23],
        className: `site-pin ${priority ? "site-pin--priority" : ""} ${planned ? "site-pin--planned" : ""} ${selected ? "site-pin--selected" : ""}`,
      })
      const marker = L.marker([location.latitude, location.longitude], {
        title: location.name,
        alt: location.name,
        icon,
        zIndexOffset: selected ? 1000 : planned ? 100 : 0,
      }).addTo(markers)
      const markerLabel = priority ? `${location.name} · Υψηλή προτεραιότητα` : location.name
      marker.getElement()?.setAttribute("aria-label", markerLabel)
      marker.bindTooltip(tooltip(markerLabel), { direction: "top" })
      marker.on("click", () => onSelectLocation(location.id))
    }
    return () => { markers.remove() }
  }, [locations, onSelectLocation, plannedIds, selectedId])

  useEffect(() => {
    const map = instance.current
    const selected = locations.find((location) => location.id === selectedId)
    if (map && selected) {
      const point: L.LatLngExpression = [selected.latitude, selected.longitude]
      if (!map.getBounds().pad(-0.15).contains(point)) map.panTo(point)
    }
  }, [locations, selectedId])

  const resetToCity = () => {
    if (areaBounds.current) {
      instance.current?.fitBounds(areaBounds.current, { maxZoom: 14, padding: [22, 38] })
    } else {
      instance.current?.setView(cityCenter, cityZoom)
    }
  }

  return (
    <div className="map-frame">
      <div className="map-canvas" ref={container} aria-label="Διαδραστικός χάρτης της Αθήνας" />
      <div className="map-tools">
        <button type="button" aria-label="Εστίαση προς τα μέσα" onClick={() => instance.current?.zoomIn()}><Plus size={18} /></button>
        <button type="button" aria-label="Εστίαση προς τα έξω" onClick={() => instance.current?.zoomOut()}><Minus size={18} /></button>
        <button type="button" aria-label="Επαναφορά χάρτη" onClick={resetToCity}><Crosshair size={18} /></button>
        <button type="button" aria-label="Επίπεδα χάρτη" aria-expanded={showLayers} onClick={() => setShowLayers(!showLayers)}><Layers3 size={18} /></button>
      </div>
      {showLayers && (
        <div className="map-layer-menu">
          <label><input type="checkbox" checked={showHeat} onChange={(event) => setShowHeat(event.target.checked)} /> Θερμοκρασία επιφάνειας</label>
          <label><input type="checkbox" checked={showCanopy} onChange={(event) => setShowCanopy(event.target.checked)} /> Δενδροκάλυψη</label>
          <label><input type="checkbox" checked={showPlantings} onChange={(event) => setShowPlantings(event.target.checked)} /> Καταγραφές φύτευσης</label>
          <label><input type="checkbox" checked={showSchools} onChange={(event) => setShowSchools(event.target.checked)} /> Δημόσια σχολεία</label>
        </div>
      )}
      {(!tilesAvailable || !heat) && (
        <div className="tile-status">{!heat ? "Φόρτωση ή απουσία θερμικού επιπέδου" : "Το βασικό υπόβαθρο δεν είναι διαθέσιμο"}</div>
      )}
      <div className="map-legend">
        {showHeat && (
          <div>
            <strong>Θερμοκρασία επιφάνειας (°C)</strong>
            <div className="legend-bands">
              {[breaks[0] - 1, ...breaks].map((value, index) => (
                <div key={value} title={index === 0 ? `Κάτω από ${temperature(breaks[0])}` : index < breaks.length ? `Από ${temperature(value)} έως κάτω από ${temperature(breaks[index])}` : `Από ${temperature(value)} και άνω`}>
                  <span style={{ background: heatColor(value, breaks) }} />
                  {index === 0 ? `<${numeric(breaks[0])}` : index === breaks.length ? `${numeric(value)}+` : numeric(value)}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="legend-features">
          {showCanopy && <span><i className="legend-swatch legend-swatch--trees" /> Δενδροκάλυψη</span>}
          {showPlantings && <span><i className="legend-swatch legend-swatch--planting" /> Καταγραφές φύτευσης</span>}
          {showSchools && <span><i className="legend-swatch legend-swatch--schools" /> Δημόσια σχολεία</span>}
          <span><i className="legend-swatch legend-swatch--candidate" /> Υποψήφια θέση</span>
          {locations.some((location) => location.priority_band === "high") && <span><i className="legend-swatch legend-swatch--priority" /> Υψηλή προτεραιότητα</span>}
          {plannedIds.length > 0 && <span><i className="legend-swatch legend-swatch--plan" /> Θέση στο πλάνο</span>}
        </div>
      </div>
      <div className="map-scale" aria-hidden="true"><span>{scale.label}</span><i style={{ width: scale.width }} /></div>
    </div>
  )
}
