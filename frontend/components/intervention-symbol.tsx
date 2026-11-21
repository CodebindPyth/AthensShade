type Appearance = { label: string; color: string; path: string; image?: string }

const greenBuilding = {
  label: "Δημοτικά κτίρια",
  color: "#27674e",
  image: "/municipal-green-building.png",
  path: "M4 20h16M6 20V10h12v10M9 13v2m6-2v2m-3 2v3m0-10V7m0 0c-3 0-5-2-5-5 3 0 5 2 5 5Zm0 0c0-3 2-5 5-5 0 3-2 5-5 5Z",
}

const civicBuildings: Record<string, Appearance> = {
  police: { label: "Αστυνομία", color: "#21488a", image: "/civic-police.png", path: "M12 2 3 6v5c0 5 4 9 9 11 5-2 9-6 9-11V6ZM12 8v7m-3.5-3.5h7" },
  fire: { label: "Πυροσβεστική", color: "#9b3e28", image: "/civic-fire.png", path: "M12 22c-5 0-8-3-8-7 0-3 2-6 4-7 0 2 1 3 2 3 3-2 4-6 4-9 4 4 6 8 6 13 0 4-3 7-8 7Z" },
  hospital: { label: "Νοσοκομεία", color: "#22746e", image: "/civic-hospital.png", path: "M4 21V5h16v16M2 21h20M9 21v-4h6v4m-3-10v4m-2-2h4" },
  kep: { label: "ΚΕΠ", color: "#654786", image: "/civic-kep.png", path: "m3 9 9-6 9 6H3Zm2 0v11m7-11v11m7-11v11M3 21h18" },
  court: { label: "Δικαστήρια", color: "#4b5563", image: "/civic-court.png", path: "M12 3v17M4 20h16M4 7h16m-1 0-3 6h6l-3-6ZM5 7l-3 6h6L5 7Z" },
}

export function civicAppearance(kind?: string): Appearance {
  return civicBuildings[kind ?? ""] ?? greenBuilding
}

const appearances = new Map<string, Appearance>([
  ["tree_planting", {
    label: "Δέντρα",
    color: "#176544",
    path: "M12 22v-5m0 0 3.5-3.5M12 17l-2.5-2.5M7 17a4 4 0 0 1-1.3-7.8A5.8 5.8 0 0 1 11.5 3a6 6 0 0 1 5.8 4.4A4.9 4.9 0 0 1 16 17h-1",
  }],
  ["shade_structure", {
    label: "Σκίαστρα",
    color: "#255794",
    path: "M3 8 6 4h12l3 4H3Zm2 0v12m14-12v12M4 20h2m12 0h2M9 4 8 8m7-4 1 4",
  }],
  ["green_roof", greenBuilding],
  ["green_facade", greenBuilding],
  ["municipal_building", greenBuilding],
  ["greenery", {
    label: "Χώροι πρασίνου",
    color: "#5b6e22",
    path: "M12 21v-8m0 2C6 15 4 12 4 8c5 0 8 3 8 7Zm0-2c0-5 3-8 8-8 0 5-3 8-8 8Z",
  }],
])

const fallback: Appearance = {
  label: "Παρέμβαση",
  color: "#46546b",
  path: "M20 10c0 5-8 10-8 10S4 15 4 10a8 8 0 1 1 16 0Z M12 10h.01",
}

export function interventionAppearance(type?: string): Appearance {
  return appearances.get(type ?? "") ?? fallback
}

export function InterventionSymbol({ type, size = 18 }: { type: string; size?: number }) {
  return <InterventionArtwork appearance={interventionAppearance(type)} size={size} />
}

export function InterventionArtwork({ appearance, size }: { appearance: Appearance; size: number }) {
  if (appearance.image) {
    return <img className="municipal-artwork" src={appearance.image} width={size} height={size} alt="" />
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={appearance.path} />
    </svg>
  )
}
