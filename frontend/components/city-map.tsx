"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import L from "leaflet"
import { Crosshair, Layers3, Minus, Plus, X } from "lucide-react"
import type { Feature, FeatureCollection } from "geojson"
import type { AirObservations, AirReading, Intervention, Location, Plan, ThermalImpact } from "../lib/api"
import { heatColor, heatThresholds, localObservationTime, numeric, shadeArea, temperature } from "../lib/format"
import { civicAppearance, InterventionArtwork, interventionAppearance } from "./intervention-symbol"
import { MunicipalPopupCard, TreePopupCard } from "./tree-popup-card"
import hotNeighborhoods from "../lib/hot-neighborhoods.json"
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
  showImpact: boolean
  hotspotThreshold?: number | null
  canopyPeriod?: string | null
  onSelectTile: (tile: TileSelection) => void
}

const cityCenter: L.LatLngExpression = [37.991, 23.731]
const cityZoom = 12
const impactLabelSize = L.point(73, 24)
const canopyBands = [
  { below: 5, label: "<5%", color: "#b2d6b1", opacity: 0.24 },
  { below: 15, label: "5–<15%", color: "#6cbe81", opacity: 0.5 },
  { below: 30, label: "15–<30%", color: "#268452", opacity: 0.65 },
  { below: 101, label: "30%+", color: "#095b3c", opacity: 0.77 },
]

type TreeSelection = { id: string; plan: Plan | null }
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

function canopyOf(feature?: Feature) {
  const percent = feature?.properties?.canopy_percent
  return typeof percent === "number" && Number.isFinite(percent) && percent >= 0 && percent <= 100 ? percent : null
}

function asText(value: unknown) {
  return typeof value === "string" ? value : null
}

function tooltip(label: string) {
  const content = document.createElement("span")
  content.textContent = label
  return content
}

function markerGlyph(appearance: ReturnType<typeof interventionAppearance>) {
  if (appearance.image) {
    return `<img class="municipal-artwork" src="${appearance.image}" width="22" height="22" alt="" />`
  }
  return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${appearance.path}" /></svg>`
}

function proposalPoint(location: Location, intervention?: Intervention) {
  const site = intervention?.siting?.evidence
  return L.latLng(site?.latitude ?? location.latitude, site?.longitude ?? location.longitude)
}

// This is a planning catchment, independent of the modeled temperature under the canopy.
const neighborhoodRadiusM = 500

function neighborhoodZone(map: L.Map, center: L.LatLng) {
  const bounds = center.toBounds(neighborhoodRadiusM * 2)
  const size = map.project(bounds.getSouthEast()).subtract(map.project(bounds.getNorthWest()))
  return L.divIcon({ className: styles.coolingZone, iconSize: size, iconAnchor: size.divideBy(2) })
}

function treeClusterGlyph(glyph: string, quantity: number) {
  // Overview symbols are part of the pin. On zoom the map shows the surveyed anchors.
  const count = Math.min(quantity, 6)
  const satellites = Array.from({ length: count }, (_, index) => {
    const angle = (index / count) * 2 * Math.PI + Math.PI / 2
    const x = Math.round(22 * Math.cos(angle))
    const y = Math.round(22 * Math.sin(angle))
    return `<i class="${styles.clusterTree}" style="left:calc(50% + ${x}px);top:calc(50% + ${y}px)">${glyph}</i>`
  }).join("")
  return `${glyph}<span aria-hidden="true">${satellites}</span><span class="${styles.pinCount}" aria-hidden="true">+${numeric(quantity)}</span>`
}

function temperatureBadge(cooling: string, offset: number) {
  return L.divIcon({
    html: tooltip(cooling), iconSize: impactLabelSize,
    iconAnchor: [impactLabelSize.x / 2, offset + impactLabelSize.y / 2],
    className: styles.impactLabel,
  })
}

function proposalAppearance(location: Location, intervention?: Intervention) {
  const type = intervention?.type
  return interventionAppearance(type === "greenery" && location.municipal_asset ? "municipal_building" : type)
}

function impactArea(intervention?: Intervention) {
  if (intervention?.shade_impact) {
    const { estimated_min_m2, estimated_max_m2, horizon } = intervention.shade_impact
    const range = shadeArea(estimated_min_m2, estimated_max_m2)
    return `Εκτιμώμενη σκιά ${range} ${horizon === "at_tree_maturity" ? "σε ώριμη κόμη" : "μετά την εγκατάσταση"}.`
  }
  if (intervention?.greened_roof_area_m2 != null) {
    const roof = `${numeric(intervention.greened_roof_area_m2)} m²`
    return `Προτεινόμενη φύτευση σε ${roof} δώματος.`
  }
  return null
}

function proposedUnits(intervention?: Intervention) {
  const count = intervention?.shade_impact?.unit_count
  if (!count) return undefined
  if (intervention.type === "tree_planting") {
    return count === 1 ? "+1 προτεινόμενο δέντρο" : `+${numeric(count)} προτεινόμενα δέντρα`
  }
  if (intervention.type === "shade_structure") {
    return count === 1 ? "+1 προτεινόμενο σκίαστρο" : `+${numeric(count)} προτεινόμενα σκίαστρα`
  }
}

function supportSpaceKey(element: HTMLElement | undefined, activate: () => void) {
  element?.addEventListener("keydown", (event) => {
    if (event.key !== " ") return
    event.preventDefault()
    event.stopPropagation()
    activate()
  })
}

function coolingLabel(impact?: ThermalImpact) {
  const min = impact?.cooling_min_c
  const max = impact?.cooling_max_c
  if (min == null || max == null) return null
  return min === max ? `−${numeric(min)} °C` : `−${numeric(min)} έως −${numeric(max)} °C`
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

export default function CityMap({ heat, trees, context, air, locations, selectedId, plan, showImpact, hotspotThreshold, canopyPeriod, onSelectTile }: MapProps) {
  const container = useRef<HTMLDivElement | null>(null)
  const instance = useRef<L.Map | null>(null)
  const areaBounds = useRef<L.LatLngBounds | null>(null)
  const thermalBounds = useRef<L.LatLngBounds | null>(null)
  const treeMarkers = useRef(new Map<string, L.Marker>())
  const municipalMarkers = useRef(new Map<string, L.Marker>())
  const treeCloseButton = useRef<HTMLButtonElement | null>(null)
  const [treeSelection, setTreeSelection] = useState<TreeSelection | null>(null)
  const [cardPosition, setCardPosition] = useState<CardPosition | null>(null)
  const [showHeat, setShowHeat] = useState(true)
  const [showCanopy, setShowCanopy] = useState(false)
  const [showPlantings, setShowPlantings] = useState(false)
  const [showMunicipal, setShowMunicipal] = useState(true)
  const [showAir, setShowAir] = useState(false)
  const [showParks, setShowParks] = useState(false)
  const [showLayers, setShowLayers] = useState(false)
  const [tilesAvailable, setTilesAvailable] = useState(true)
  const [scale, setScale] = useState({ label: "1 km", width: 95 })
  const breaks = useMemo(() => heatThresholds(heat?.features.flatMap((feature) => temperatureOf(feature) ?? []) ?? [], hotspotThreshold), [heat, hotspotThreshold])
  const interventionByLocation = useMemo(() => new Map(plan?.selected
    .map((row) => [row.location_id, row])), [plan])
  const plannedLocations = useMemo(() => locations.filter((location) => interventionByLocation.has(location.id)), [locations, interventionByLocation])
  const visibleMunicipalLocations = useMemo(() => showMunicipal ? locations.filter((location) => (
    location.municipal_asset && location.heat_c != null && location.heat_c > 35
      && location.heat_c >= breaks[2] && !interventionByLocation.has(location.id)
  )) : [], [breaks, interventionByLocation, locations, showMunicipal])
  const impactByLocation = useMemo(() => new Map(
    plan?.thermal_impact?.flatMap((impact) => impact.location_ids.map((id) => [id, impact] as const)),
  ), [plan])
  const visibleMarkerStyles = [...new Set([
    ...plannedLocations.map((location) => proposalAppearance(location, interventionByLocation.get(location.id))),
    ...visibleMunicipalLocations.map((location) => civicAppearance(location.municipal_asset?.kind)),
  ])]
  const activeTree = treeSelection && treeSelection.plan === plan
    ? plannedLocations.find((location) => location.id === treeSelection.id)
      ?? visibleMunicipalLocations.find((location) => location.id === treeSelection.id)
      ?? null
    : null
  const activeIntervention = activeTree ? interventionByLocation.get(activeTree.id) : undefined
  const activeImpact = activeTree && showImpact ? impactByLocation.get(activeTree.id) : undefined
  const activeArea = showImpact ? impactArea(activeIntervention) : null
  const activeUnits = showImpact ? proposedUnits(activeIntervention) : null
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
    for (const [name, zIndex] of [["heat", 380], ["context", 410], ["trees", 420], ["plantings", 425], ["cooling-zones", 435], ["neighborhood-labels", 605], ["proposal-anchors", 500], ["impact-labels", 625]] as const) {
      map.createPane(name).style.zIndex = String(zIndex)
    }
    map.getPane("plantings")?.style.setProperty("pointer-events", "none")
    map.getPane("neighborhood-labels")?.style.setProperty("pointer-events", "none")
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
      map.getContainer().classList.toggle(styles.detailedPlantings, map.getZoom() >= 15.5)
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
      filter: (feature) => !!feature.geometry && feature.geometry.type !== "Point",
      style: (feature) => {
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
  }, [context])

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
        if (value !== null && !showImpact) shape.bindTooltip(tooltip(temperature(value)), { sticky: true, direction: "top" })
      },
    }).addTo(map)
    if (!thermalBounds.current && layer.getBounds().isValid()) {
      thermalBounds.current = layer.getBounds()
      if (!areaBounds.current) fitCity(map, thermalBounds.current)
    }
    return () => { layer.remove() }
  }, [breaks, heat, onSelectTile, showHeat, showImpact])

  useEffect(() => {
    const map = instance.current
    if (!map || !heat || !showHeat) return
    const labels = L.layerGroup().addTo(map)
    const place = () => {
      labels.clearLayers()
      const occupied: L.Point[] = []
      const bounds = map.getBounds()
      for (const { name, latitude, longitude, heat_c } of hotNeighborhoods) {
        if (heat_c < breaks[2]) continue
        const point = L.latLng(latitude, longitude)
        if (!bounds.contains(point)) continue
        const position = map.latLngToContainerPoint(point)
        if (occupied.some((other) => Math.abs(other.x - position.x) < 126 && Math.abs(other.y - position.y) < 35)) continue
        occupied.push(position)
        L.marker(point, {
          pane: "neighborhood-labels", interactive: false, keyboard: false,
          icon: L.divIcon({ className: styles.neighborhoodName, html: tooltip(name), iconSize: [0, 0], iconAnchor: [0, 0] }),
        }).addTo(labels)
      }
    }
    place()
    map.on("moveend", place)
    return () => { map.off("moveend", place); labels.remove() }
  }, [breaks, heat, showHeat])

  useEffect(() => {
    const map = instance.current
    if (!map || !trees || !showCanopy) return
    const renderer = L.canvas({ pane: "trees" })
    const layer = L.geoJSON(trees, {
      pane: "trees",
      filter: (feature) => feature.properties?.kind === "canopy" && canopyOf(feature) !== null,
      style: (feature) => {
        const percent = canopyOf(feature) ?? 0
        const band = canopyBands.find(({ below }) => percent < below) ?? canopyBands[0]
        return {
          renderer, color: band.color, weight: percent >= 15 ? 0.6 : 0,
          fillColor: band.color, fillOpacity: percent === 0 ? 0 : band.opacity,
        }
      },
      onEachFeature: (feature, shape) => {
        const percent = canopyOf(feature)
        if (percent === null) return
        const label = `Δενδροκάλυψη κελιού · ${numeric(percent)}%${canopyPeriod ? ` (${canopyPeriod})` : ""}`
        shape.bindTooltip(tooltip(label), { sticky: true, direction: "top" })
        shape.bindPopup(tooltip(label))
      },
    }).addTo(map)
    return () => { layer.remove(); renderer.remove() }
  }, [trees, showCanopy, canopyPeriod])

  useEffect(() => {
    const map = instance.current
    if (!map || !trees || !showPlantings) return
    const renderer = L.canvas({ pane: "plantings" })
    const layer = L.geoJSON(trees, {
      pane: "plantings",
      interactive: false,
      filter: (feature) => feature.geometry?.type === "Point" && feature.properties?.kind === "planting",
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
        pane: "plantings",
        renderer,
        radius: 2.1,
        color: "#0d613d",
        fillColor: "#58ca71",
        fillOpacity: 0.92,
        weight: 0.9,
        interactive: false,
      }),
    }).addTo(map)
    return () => { layer.remove(); renderer.remove() }
  }, [trees, showPlantings])

  useEffect(() => {
    const map = instance.current
    if (!map || visibleMunicipalLocations.length === 0) return
    const buildings = L.layerGroup().addTo(map)
    const byId = new Map<string, L.Marker>()
    for (const location of visibleMunicipalLocations) {
      const appearance = civicAppearance(location.municipal_asset?.kind)
      const title = `${appearance.label} · ${location.name}${showImpact ? " · Μελέτη δέντρων και φυτεμένου δώματος" : ""}`
      const icon = L.divIcon({
        html: markerGlyph(appearance), className: `${styles.treePin}${showImpact ? ` ${styles.civicImpactPin}` : ""}`,
        iconSize: [28, 28], iconAnchor: [14, 14],
      })
      const marker = L.marker(proposalPoint(location), {
        icon, title, riseOnHover: true, zIndexOffset: location.municipal_asset?.kind === "school" ? 50 : 1000,
      }).addTo(buildings)
      const element = marker.getElement()
      element?.setAttribute("aria-label", title)
      element?.setAttribute("aria-expanded", "false")
      element?.setAttribute("data-municipal-location", location.id)
      element?.setAttribute("data-facility-kind", location.municipal_asset?.kind ?? "building")
      if (showImpact) element?.setAttribute("data-impact-facility", location.id)
      element?.style.setProperty("--intervention-color", appearance.color)
      const toggle = () => setTreeSelection((previous) => (
        previous?.plan === plan && previous.id === location.id ? null : { id: location.id, plan }
      ))
      marker.on("click", toggle)
      supportSpaceKey(element, toggle)
      byId.set(location.id, marker)
    }
    const spaceSchoolPins = () => {
      const occupied = [...byId].filter(([id]) => !id.startsWith("school-atlas-"))
        .map(([, pin]) => map.project(pin.getLatLng()))
      const spacing = map.getZoom() >= 16 ? 12 : 22
      for (const [id, pin] of byId) {
        if (!id.startsWith("school-atlas-")) continue
        const position = map.project(pin.getLatLng())
        const hide = occupied.some((other) => other.distanceTo(position) < spacing)
        const element = pin.getElement()
        if (element) element.hidden = hide
        if (!hide) occupied.push(position)
      }
    }
    spaceSchoolPins()
    map.on("zoomend", spaceSchoolPins)
    municipalMarkers.current = byId
    return () => {
      map.off("zoomend", spaceSchoolPins)
      buildings.remove()
      municipalMarkers.current = new Map()
    }
  }, [plan, showImpact, visibleMunicipalLocations])

  useEffect(() => {
    const map = instance.current
    setTreeSelection(null)
    if (!map || !plan) return
    fitCity(map, areaBounds.current ?? thermalBounds.current)
    const markers = L.layerGroup().addTo(map)
    const byId = new Map<string, L.Marker>()
    for (const location of plannedLocations) {
      const priority = location.priority_band === "high"
      const intervention = interventionByLocation.get(location.id)
      const type = intervention?.type ?? ""
      const appearance = proposalAppearance(location, intervention)
      const quantity = intervention?.shade_impact?.unit_count
      const label = [location.name, proposedUnits(intervention) ?? appearance.label].join(" · ")
      const icon = L.divIcon({
        html: quantity && type === "tree_planting"
          ? treeClusterGlyph(markerGlyph(appearance), quantity)
          : markerGlyph(appearance),
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        className: styles.treePin,
      })
      const marker = L.marker(proposalPoint(location, intervention), {
        title: label,
        icon,
        riseOnHover: true,
        zIndexOffset: priority ? 1800 : 1700,
      }).addTo(markers)
      const element = marker.getElement()
      element?.setAttribute("aria-label", label)
      element?.setAttribute("aria-expanded", "false")
      element?.setAttribute("data-tree-location", location.id)
      element?.setAttribute("data-intervention-type", type)
      if (location.municipal_asset) element?.setAttribute("data-facility-kind", location.municipal_asset.kind)
      const anchor = marker.getLatLng()
      element?.setAttribute("data-site-latitude", String(anchor.lat))
      element?.setAttribute("data-site-longitude", String(anchor.lng))
      element?.style.setProperty("--intervention-color", appearance.color)
      marker.on("click", () => setTreeSelection((previous) => (
        previous?.plan === plan && previous.id === location.id ? null : { id: location.id, plan }
      )))
      supportSpaceKey(element, () => marker.fire("click"))
      byId.set(location.id, marker)
    }
    treeMarkers.current = byId
    return () => {
      markers.remove()
      treeMarkers.current = new Map()
    }
  }, [interventionByLocation, plan, plannedLocations])

  useEffect(() => {
    const map = instance.current
    if (!map || !plan) return
    const anchors = L.layerGroup().addTo(map)
    const place = () => {
      anchors.clearLayers()
      if (map.getZoom() < 15.5) return
      const view = map.getBounds().pad(0.15)
      const closeView = map.getZoom() >= 17
      for (const item of plan.selected) {
        const appearance = interventionAppearance(item.type)
        const isTree = item.type === "tree_planting"
        const units = proposedUnits(item)
        for (const { latitude, longitude } of item.siting?.anchors ?? []) {
          const latLng = L.latLng(latitude, longitude)
          if (!view.contains(latLng)) continue
          const point = closeView ? L.marker(latLng, {
            pane: "proposal-anchors", title: isTree ? "Προτεινόμενο δέντρο" : "Προτεινόμενο σκίαστρο",
            icon: L.divIcon({ className: `${styles.unitPin}${isTree ? ` ${styles.whiteTree}` : ""}`, html: markerGlyph(appearance), iconSize: [14, 14], iconAnchor: [7, 7] }),
          }).addTo(anchors) : L.circleMarker(latLng, {
            pane: "proposal-anchors", radius: 4, color: "white", weight: 1.3,
            fillColor: appearance.color, fillOpacity: 1, bubblingMouseEvents: false,
          }).addTo(anchors)
          point.getElement()?.setAttribute("data-proposal-anchor", item.location_id)
          if (units) point.bindTooltip(tooltip(units))
          point.on("click", () => setTreeSelection({ id: item.location_id, plan }))
        }
      }
    }
    place()
    map.on("moveend", place)
    return () => { map.off("moveend", place); anchors.remove() }
  }, [plan])

  useEffect(() => {
    const map = instance.current
    if (!map || !plan || !showImpact || plannedLocations.length === 0) return
    const previousView = { center: map.getCenter(), zoom: map.getZoom() }
    const size = map.getSize()
    const focus = L.latLngBounds(plannedLocations.map((location) => (
      proposalPoint(location, interventionByLocation.get(location.id))
    )))
    map.fitBounds(focus, {
      padding: [Math.min(102, size.x / 4), Math.min(102, size.y / 4)],
      maxZoom: 15,
      animate: false,
    })
    const geometry = L.layerGroup().addTo(map)
    const zones = plannedLocations.map((location) => {
      const intervention = interventionByLocation.get(location.id)
      const actual = proposalPoint(location, intervention)
      const impact = impactByLocation.get(location.id)
      const minimum = impact?.cooling_min_c
      const cooling = minimum == null ? null : `−${temperature(minimum)}`
      const open = () => setTreeSelection({ id: location.id, plan })
      const center = intervention?.siting?.anchors?.length
        ? L.latLngBounds(intervention.siting.anchors.map(({ latitude, longitude }) => L.latLng(latitude, longitude))).getCenter()
        : actual
      const zone = intervention?.type === "tree_planting" ? L.marker(center, {
        pane: "cooling-zones", icon: neighborhoodZone(map, center), interactive: false, keyboard: false,
      }).addTo(geometry) : null
      const title = [location.name, coolingLabel(impact), impact?.metric].filter(Boolean).join(" · ")
      const badge = cooling ? L.marker(actual, {
        pane: "impact-labels", title, alt: title, icon: temperatureBadge(cooling, 33),
      }).addTo(geometry).on("click", open) : null
      if (badge) {
        const element = badge.getElement()
        element?.setAttribute("aria-label", title)
        element?.setAttribute("data-impact-location", location.id)
        supportSpaceKey(element, open)
      }
      return { location, center, zone }
    })

    const placeZones = () => {
      for (const { location, center, zone } of zones) {
        if (!zone) continue
        zone.setIcon(neighborhoodZone(map, center))
        zone.getElement()?.setAttribute("data-cooling-zone", location.id)
      }
    }
    placeZones()
    map.on("zoomend", placeZones)
    return () => {
      map.off("zoomend", placeZones)
      geometry.remove()
      if (instance.current === map) map.setView(previousView.center, previousView.zoom, { animate: false })
    }
  }, [impactByLocation, interventionByLocation, plan, plannedLocations, showImpact])

  useEffect(() => {
    for (const [id, marker] of treeMarkers.current) {
      const element = marker.getElement()
      element?.setAttribute("aria-expanded", String(id === activeTree?.id))
      if (element?.hasAttribute("data-facility-kind")) {
        element.classList.toggle(styles.civicImpactPin, showImpact)
        if (showImpact) element.setAttribute("data-impact-facility", id)
        else element.removeAttribute("data-impact-facility")
      }
    }
    for (const [id, marker] of municipalMarkers.current) {
      marker.getElement()?.setAttribute("aria-expanded", String(id === activeTree?.id))
    }
  }, [activeTree, plan, showImpact])

  useEffect(() => {
    const map = instance.current
    if (!map || !activeTree) return
    const coordinates = () => (
      treeMarkers.current.get(activeTree.id)?.getLatLng()
      ?? municipalMarkers.current.get(activeTree.id)?.getLatLng()
      ?? proposalPoint(activeTree, interventionByLocation.get(activeTree.id))
    )
    const size = map.getSize()
    const point = map.latLngToContainerPoint(coordinates())
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
      const pin = map.latLngToContainerPoint(coordinates())
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
    map.on("move zoom zoomend resize", update)
    return () => { map.off("move zoom zoomend resize", update) }
  }, [activeTree, interventionByLocation])

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
    if ((plan && treeMarkers.current.has(selectedId)) || municipalMarkers.current.has(selectedId)) {
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
    if (activeTree) {
      const marker = treeMarkers.current.get(activeTree.id) ?? municipalMarkers.current.get(activeTree.id)
      marker?.getElement()?.focus({ preventScroll: true })
    }
  }

  return (
    <div className="map-frame">
      <div className={`map-canvas ${styles.mapCanvas}`} ref={container} aria-label="Διαδραστικός χάρτης της Αθήνας" />
      {activeTree && cardPosition && (
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
            {activeIntervention?.type === "tree_planting" && (
              <button type="button" className={styles.zoomToTrees} onClick={() => instance.current?.setView(proposalPoint(activeTree, activeIntervention), 18)}>
                <Crosshair size={13} aria-hidden="true" /> Εστίαση στις θέσεις φύτευσης
              </button>
            )}
            {(activeImpact || activeArea) && (
              <section className={styles.impactDetail} aria-label="Υποθετική τοπική ψύξη">
                <strong>{coolingLabel(activeImpact) ?? "Χωρίς αριθμητική εκτίμηση"}</strong>
                {activeUnits && <p className={styles.impactUnits}>{activeUnits}</p>}
                {activeArea && <p className={styles.impactArea}>{activeArea}</p>}
                {activeImpact && <p>{activeImpact.metric}. {activeImpact.evidence}</p>}
                {activeImpact?.evidence_url && (
                  <a href={activeImpact.evidence_url} rel="noreferrer" target="_blank">Μελέτη αναφοράς</a>
                )}
              </section>
            )}
            {plan && interventionByLocation.has(activeTree.id)
              ? <TreePopupCard key={activeTree.id} location={activeTree} plan={plan} showImpact={showImpact} />
              : <MunicipalPopupCard key={activeTree.id} location={activeTree} showImpact={showImpact} />}
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
          {showCanopy && <p className={styles.canopyHint}>Πάτησε ένα κελί για το ποσοστό κάλυψης.</p>}
          <label><input type="checkbox" checked={showPlantings} onChange={(event) => setShowPlantings(event.target.checked)} /> Καταγραφές φύτευσης</label>
          <label><input type="checkbox" checked={showParks} onChange={(event) => setShowParks(event.target.checked)} /> Πάρκα τσέπης</label>
          <label><input type="checkbox" checked={showMunicipal} onChange={(event) => setShowMunicipal(event.target.checked)} /> Δημόσιες υπηρεσίες σε κόκκινες ζώνες</label>
        </div>
      )}
      {(!tilesAvailable || !heat) && (
        <div className="tile-status">{!heat ? "Φόρτωση ή απουσία θερμικού επιπέδου" : "Το βασικό υπόβαθρο δεν είναι διαθέσιμο"}</div>
      )}
      <div className={`map-legend${showCanopy || visibleMarkerStyles.length > 0 ? ` ${styles.combinedLegend}` : ""}`}>
        {showImpact && plannedLocations.length > 0 && (
          <div className={styles.impactLegend} aria-label="Υπόμνημα επίδρασης">
            <i aria-hidden="true" />
            <div>
              <strong>Υποθετική τοπική ψύξη</strong>
              <span>Μπλε ζώνη μελέτης · ακτίνα {numeric(neighborhoodRadiusM)} μ. Η ένδειξη °C αφορά την εκτιμώμενη ψύξη στο σημείο φύτευσης ή σκίασης.</span>
            </div>
          </div>
        )}
        {showHeat && (
          <div>
            <strong>{showImpact ? "Ιστορική θερμοκρασία επιφάνειας (°C)" : "Θερμοκρασία επιφάνειας (°C)"}</strong>
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
        {showCanopy && (
          <div className={styles.canopyLegend}>
            <strong>Δενδροκάλυψη{canopyPeriod ? ` · ${canopyPeriod}` : ""}</strong>
            <div className="legend-bands">
              {canopyBands.map(({ label, color }) => (
                <div key={label}><span style={{ background: color }} />{label}</div>
              ))}
            </div>
          </div>
        )}
        <div className={`legend-features ${styles.legendFeatures}`}>
          {showAir && !!air?.readings.length && <span><i className="legend-swatch legend-swatch--air" /> Θερμοκρασία αέρα</span>}
          {showPlantings && <span><i className="legend-swatch legend-swatch--planting" /> Καταγραφές φύτευσης</span>}
          {showParks && <span><i className="legend-swatch legend-swatch--park" /> Πάρκο τσέπης</span>}
        </div>
        {visibleMarkerStyles.length > 0 && (
          <div className={`legend-features ${styles.planLegend}`} aria-label="Σύμβολα παρεμβάσεων">
            {visibleMarkerStyles.map((appearance) => (
              <span key={appearance.label}>
                <i className={styles.legendPin} style={{ backgroundColor: appearance.color }} aria-hidden="true">
                  <InterventionArtwork appearance={appearance} size={13} />
                </i>
                {appearance.label}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="map-scale" aria-hidden="true"><span>{scale.label}</span><i style={{ width: scale.width }} /></div>
    </div>
  )
}
