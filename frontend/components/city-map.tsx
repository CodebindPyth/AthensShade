"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import L from "leaflet"
import { Crosshair, Layers3, Minus, Plus, TreeDeciduous, X } from "lucide-react"
import type { Feature, FeatureCollection } from "geojson"
import type { AirObservations, AirReading, Location, Plan } from "../lib/api"
import { heatColor, heatThresholds, localObservationTime, numeric, temperature } from "../lib/format"
import { TreePopupCard } from "./tree-popup-card"
import styles from "./city-map.module.css"

export type TileSelection = { temperature: number | null; sourceId: string | null; name?: string }

type MapProps = {
  heat?: FeatureCollection
  trees?: FeatureCollection
  context?: FeatureCollection
  air?: AirObservations | null
  locations: Location[]
  selectedId: string | null
  plan: Plan | null
  hotspotThreshold?: number | null
  onSelectTile: (tile: TileSelection) => void
}

const cityCenter: L.LatLngExpression = [37.991, 23.731]
const cityZoom = 12
const treeGlyph = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22v-5m0 0 3.5-3.5M12 17l-2.5-2.5M7 17a4 4 0 0 1-1.3-7.8A5.8 5.8 0 0 1 11.5 3a6 6 0 0 1 5.8 4.4A4.9 4.9 0 0 1 16 17h-1"/></svg>'

type TreeSelection = { id: string; plan: Plan }
type CardPosition = { left: number; top: number; width: number; height: number; anchor: number }

function fitCity(map: L.Map, bounds: L.LatLngBounds | null) {
  if (bounds) map.fitBounds(bounds, { maxZoom: 14, padding: [22, 38], animate: false })
  else map.setView(cityCenter, cityZoom, { animate: false })
}

function treeCardWidth(mapWidth: number) {
  return Math.max(1, Math.min(302, mapWidth - 24))
}

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

function airPopup(reading: AirReading, air: AirObservations) {
  const content = document.createElement("div")
  content.className = "air-popup"
  const name = document.createElement("strong")
  name.textContent = reading.station_name
  const measurement = document.createElement("span")
  measurement.textContent = `Θερμοκρασία αέρα · ${temperature(reading.temperature_c)}`
  const date = document.createElement("time")
  date.dateTime = reading.observed_at
  date.textContent = `${localObservationTime(reading.observed_at)} (ώρα Αθήνας)`
  content.append(name, measurement, date)
  if (reading.humidity_pct !== null) content.append(tooltip(`Σχετική υγρασία · ${numeric(reading.humidity_pct)}%`))
  if (reading.origin !== "api") content.append(tooltip("Αποθηκευμένη παρατήρηση"))
  content.append(tooltip("Ο δείκτης τοποθετείται στο αντίστοιχο σημείο αναφοράς της περιοχής."))
  const source = document.createElement("a")
  source.href = air.source_url
  source.target = "_blank"
  source.rel = "noopener noreferrer"
  source.textContent = "Πηγή · Δήμος Αθηναίων"
  content.append(source)
  return content
}

export default function CityMap({ heat, trees, context, air, locations, selectedId, plan, hotspotThreshold, onSelectTile }: MapProps) {
  const container = useRef<HTMLDivElement | null>(null)
  const instance = useRef<L.Map | null>(null)
  const areaBounds = useRef<L.LatLngBounds | null>(null)
  const thermalBounds = useRef<L.LatLngBounds | null>(null)
  const treeMarkers = useRef(new Map<string, L.Marker>())
  const treeCloseButton = useRef<HTMLButtonElement | null>(null)
  const [treeSelection, setTreeSelection] = useState<TreeSelection | null>(null)
  const [cardPosition, setCardPosition] = useState<CardPosition | null>(null)
  const [showHeat, setShowHeat] = useState(true)
  const [showCanopy, setShowCanopy] = useState(false)
  const [showPlantings, setShowPlantings] = useState(false)
  const [showSchools, setShowSchools] = useState(false)
  const [showAir, setShowAir] = useState(false)
  const [showParks, setShowParks] = useState(false)
  const [showLayers, setShowLayers] = useState(false)
  const [tilesAvailable, setTilesAvailable] = useState(true)
  const [scale, setScale] = useState({ label: "1 km", width: 95 })
  const breaks = useMemo(() => heatThresholds(heat?.features.flatMap((feature) => temperatureOf(feature) ?? []) ?? [], hotspotThreshold), [heat, hotspotThreshold])
  const plannedLocations = useMemo(() => {
    const ids = new Set(plan?.selected.map((row) => row.location_id))
    return locations.filter((location) => ids.has(location.id))
  }, [locations, plan])
  const activeTree = treeSelection?.plan === plan
    ? plannedLocations.find((location) => location.id === treeSelection.id) ?? null
    : null
  const cardVisible = cardPosition !== null

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
    const dismissTree = () => setTreeSelection(null)
    map.on("click popupopen", dismissTree)
    const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resize.observe(container.current)
    return () => {
      resize.disconnect()
      map.remove()
      instance.current = null
      areaBounds.current = null
      thermalBounds.current = null
    }
  }, [])

  useEffect(() => {
    const map = instance.current
    if (!map || !context) return
    const shapes = L.geoJSON(context, {
      pane: "context",
      interactive: false,
      filter: (feature) => !!feature.geometry && feature.properties?.kind !== "pocket_park"
        && (feature.properties?.kind !== "school" || showSchools),
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
    const bounds = L.latLngBounds([])
    shapes.eachLayer((shape) => {
      if ("feature" in shape && "getBounds" in shape && typeof shape.getBounds === "function") {
        const feature = shape.feature as Feature
        if (feature.properties?.kind === "district" || feature.properties?.kind === "boundary" || feature.properties?.boundary) {
          bounds.extend(shape.getBounds())
        }
      }
    })
    if (bounds.isValid() && !areaBounds.current) {
      areaBounds.current = bounds
      fitCity(map, bounds)
    }
    return () => { shapes.remove() }
  }, [context, showSchools])

  useEffect(() => {
    const map = instance.current
    if (!showParks || !map || !context) return
    const parks = L.geoJSON(context, {
      filter: (feature) => feature.geometry?.type === "Point" && feature.properties?.kind === "pocket_park",
      pointToLayer: (feature, point) => {
        const name = asText(feature.properties?.name) ?? "Πάρκο τσέπης"
        const street = asText(feature.properties?.street)
        const icon = L.divIcon({ iconSize: [12, 12], className: "pocket-park-marker" })
        return L.marker(point, { icon, title: name, alt: name })
          .bindPopup(tooltip(street ? `${name} · ${street}` : name))
      },
    }).addTo(map)
    return () => { parks.remove() }
  }, [context, showParks])

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
    if (!thermalBounds.current && layer.getBounds().isValid()) {
      thermalBounds.current = layer.getBounds()
      if (!areaBounds.current) fitCity(map, thermalBounds.current)
    }
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
    setTreeSelection(null)
    if (!map || !plan) return
    fitCity(map, areaBounds.current ?? thermalBounds.current)
    const markers = L.layerGroup().addTo(map)
    const byId = new Map<string, L.Marker>()
    const icon = L.divIcon({
      html: treeGlyph,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      className: styles.treePin,
    })
    for (const location of plannedLocations) {
      const priority = location.priority_band === "high"
      const label = `Πρόταση για ${location.name}`
      const marker = L.marker([location.latitude, location.longitude], {
        title: label,
        icon,
        riseOnHover: true,
        zIndexOffset: priority ? 300 : 200,
      }).addTo(markers)
      const element = marker.getElement()
      element?.setAttribute("aria-label", label)
      element?.setAttribute("aria-expanded", "false")
      element?.setAttribute("data-tree-location", location.id)
      marker.on("click", () => setTreeSelection((previous) => (
        previous?.plan === plan && previous.id === location.id ? null : { id: location.id, plan }
      )))
      element?.addEventListener("keydown", (event) => {
        if (event.key !== " ") return
        event.preventDefault()
        event.stopPropagation()
        marker.fire("click")
      })
      byId.set(location.id, marker)
    }
    treeMarkers.current = byId
    return () => {
      markers.remove()
      treeMarkers.current = new Map()
    }
  }, [plan, plannedLocations])

  useEffect(() => {
    for (const [id, marker] of treeMarkers.current) {
      marker.getElement()?.setAttribute("aria-expanded", String(id === activeTree?.id))
    }
  }, [activeTree, plan])

  useEffect(() => {
    const map = instance.current
    if (!map || !activeTree) return
    const coordinates: L.LatLngExpression = [activeTree.latitude, activeTree.longitude]
    const size = map.getSize()
    const point = map.latLngToContainerPoint(coordinates)
    const width = treeCardWidth(size.x)
    const minX = 12 + width / 2
    const maxX = size.x - minX
    const maxY = size.y - Math.min(350, size.y - 50) - 28
    const offset = point.subtract(L.point(
      Math.max(minX, Math.min(maxX, point.x)),
      Math.max(36, Math.min(maxY, point.y)),
    ))
    if (offset.x || offset.y) map.panBy(offset, { animate: false })

    const update = () => {
      const currentSize = map.getSize()
      const pin = map.latLngToContainerPoint(coordinates)
      const cardWidth = treeCardWidth(currentSize.x)
      const left = Math.max(12, Math.min(currentSize.x - 12 - cardWidth, pin.x - cardWidth / 2))
      const top = pin.y + 23
      if (pin.x < 0 || pin.x > currentSize.x || pin.y < 0 || top > currentSize.y - 75) {
        setCardPosition(null)
        return
      }
      setCardPosition({
        left, top, width: cardWidth, height: currentSize.y - top - 28,
        anchor: Math.max(9, Math.min(cardWidth - 9, pin.x - left)),
      })
    }
    update()
    map.on("move zoom resize", update)
    return () => { map.off("move zoom resize", update) }
  }, [activeTree])

  useEffect(() => {
    if (activeTree && cardVisible) treeCloseButton.current?.focus({ preventScroll: true })
    // The initial placement shows the close control. Subsequent map moves preserve focus.
  }, [activeTree, cardVisible])

  useEffect(() => {
    const map = instance.current
    if (!map || !showAir || !air?.readings.length) return
    const byLocation = new Map(locations.map((location) => [location.id, location]))
    const layer = L.layerGroup().addTo(map)
    for (const reading of air.readings) {
      const anchor = byLocation.get(reading.location_id)
      if (!anchor) continue
      const label = `${reading.station_name}, θερμοκρασία αέρα ${temperature(reading.temperature_c)}`
      const icon = L.divIcon({
        html: tooltip("°"),
        iconSize: [18, 18],
        iconAnchor: [-7, 18],
        popupAnchor: [16, -18],
        className: "air-station",
      })
      const marker = L.marker([anchor.latitude, anchor.longitude], { icon, title: label, alt: label, zIndexOffset: 150 })
        .bindPopup(airPopup(reading, air), { maxWidth: 240 })
        .addTo(layer)
      marker.getElement()?.setAttribute("aria-label", label)
    }
    return () => { layer.remove() }
  }, [air, locations, showAir])

  useEffect(() => {
    const map = instance.current
    if (!map || !selectedId) return
    const selected = locations.find((location) => location.id === selectedId)
    if (!selected) return
    const point: L.LatLngExpression = [selected.latitude, selected.longitude]
    if (plan && treeMarkers.current.has(selectedId)) {
      setTreeSelection({ id: selectedId, plan })
    } else if (!map.getBounds().pad(-0.15).contains(point)) {
      map.panTo(point)
    }
  }, [locations, selectedId, plan])

  const resetToCity = () => {
    setTreeSelection(null)
    if (instance.current) fitCity(instance.current, areaBounds.current ?? thermalBounds.current)
  }

  const closeTree = () => {
    setTreeSelection(null)
    if (activeTree) treeMarkers.current.get(activeTree.id)?.getElement()?.focus({ preventScroll: true })
  }

  return (
    <div className="map-frame">
      <div className={`map-canvas ${styles.mapCanvas}`} ref={container} aria-label="Διαδραστικός χάρτης της Αθήνας" />
      {plan && activeTree && cardPosition && (
        <div
          className={styles.treePopup}
          data-tree-popup={activeTree.id}
          role="dialog"
          aria-label={`Παρέμβαση · ${activeTree.name}`}
          style={{ left: cardPosition.left, top: cardPosition.top, width: cardPosition.width }}
          onKeyDown={(event) => {
            if (event.key === "Escape") closeTree()
          }}
        >
          <span className={styles.treePopupArrow} style={{ left: cardPosition.anchor }} aria-hidden="true" />
          <button className={styles.treePopupClose} type="button" aria-label="Κλείσιμο κάρτας παρέμβασης" ref={treeCloseButton} onClick={closeTree}><X size={16} /></button>
          <div className={styles.treePopupScroll} style={{ maxHeight: cardPosition.height }} tabIndex={0}>
            <TreePopupCard key={activeTree.id} location={activeTree} plan={plan} />
          </div>
        </div>
      )}
      <div className="map-tools">
        <button type="button" aria-label="Εστίαση προς τα μέσα" onClick={() => instance.current?.zoomIn()}><Plus size={18} /></button>
        <button type="button" aria-label="Εστίαση προς τα έξω" onClick={() => instance.current?.zoomOut()}><Minus size={18} /></button>
        <button type="button" aria-label="Επαναφορά χάρτη" onClick={resetToCity}><Crosshair size={18} /></button>
        <button type="button" aria-label="Επίπεδα χάρτη" aria-expanded={showLayers} onClick={() => setShowLayers(!showLayers)}><Layers3 size={18} /></button>
      </div>
      {showLayers && (
        <div className="map-layer-menu">
          <label><input type="checkbox" checked={showHeat} onChange={(event) => setShowHeat(event.target.checked)} /> Θερμοκρασία επιφάνειας</label>
          <label><input type="checkbox" checked={showAir} onChange={(event) => setShowAir(event.target.checked)} /> Μετρήσεις αέρα</label>
          {showAir && !air?.readings.length && (
            <p className="air-layer-status" role="status">{air === undefined ? "Φόρτωση μετρήσεων…" : "Δεν υπάρχουν διαθέσιμες μετρήσεις."}</p>
          )}
          <label><input type="checkbox" checked={showCanopy} onChange={(event) => setShowCanopy(event.target.checked)} /> Δενδροκάλυψη</label>
          <label><input type="checkbox" checked={showPlantings} onChange={(event) => setShowPlantings(event.target.checked)} /> Καταγραφές φύτευσης</label>
          <label><input type="checkbox" checked={showParks} onChange={(event) => setShowParks(event.target.checked)} /> Πάρκα τσέπης</label>
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
        <div className={`legend-features ${styles.legendFeatures}`}>
          {showAir && !!air?.readings.length && <span><i className="legend-swatch legend-swatch--air" /> Θερμοκρασία αέρα</span>}
          {showCanopy && <span><i className="legend-swatch legend-swatch--trees" /> Δενδροκάλυψη</span>}
          {showPlantings && <span><i className="legend-swatch legend-swatch--planting" /> Καταγραφές φύτευσης</span>}
          {showParks && <span><i className="legend-swatch legend-swatch--park" /> Πάρκο τσέπης</span>}
          {showSchools && <span><i className="legend-swatch legend-swatch--schools" /> Δημόσια σχολεία</span>}
          {plannedLocations.length > 0 && <span><TreeDeciduous className={styles.legendTree} size={14} aria-hidden="true" /> Θέση στο πλάνο</span>}
        </div>
      </div>
      <div className="map-scale" aria-hidden="true"><span>{scale.label}</span><i style={{ width: scale.width }} /></div>
    </div>
  )
}
