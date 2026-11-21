const currencyFormat = new Intl.NumberFormat("el-GR", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

const numberFormat = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2 })
const observationTime = new Intl.DateTimeFormat("el-GR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Athens",
})

export const euros = (value: number) => currencyFormat.format(value)
export const numeric = (value: number) => numberFormat.format(value)
export const temperature = (value: number) => `${numeric(value)} °C`
export function localObservationTime(timestamp: string) {
  const date = new Date(timestamp)
  return Number.isFinite(date.getTime()) ? observationTime.format(date) : "Άγνωστη ώρα"
}
export const shadeArea = (lower: number, upper: number) => lower === upper ? `${numeric(lower)} m²` : `${numeric(lower)}–${numeric(upper)} m²`

const typeLabels: Record<string, string> = {
  tree_planting: "Φύτευση δέντρων",
  shade_structure: "Εγκατάσταση σκιάστρου",
  greenery: "Προσθήκη πρασίνου",
  green_roof: "Φυτεμένο δώμα",
  pocket_park: "Μικρός χώρος πρασίνου",
  cool_materials: "Ψυχρά υλικά",
}

export const interventionLabel = (type: string) => typeLabels[type] ?? "Παρέμβαση σκίασης"

export function shadeLabel(status: string) {
  if (status === "present") return "Καταγεγραμμένη σκίαση"
  if (status === "deficit") return "Έλλειψη σκίασης"
  return "Άγνωστη κάλυψη σκίασης"
}

export function feasibilityLabel(status: string) {
  if (status === "verified") return "Επιβεβαιωμένη θέση"
  if (status === "unsuitable") return "Μη κατάλληλη θέση"
  return "Χρειάζεται αυτοψία"
}

export function heatThresholds(values: number[], hotspotThreshold?: number | null): [number, number, number, number] {
  if (values.length < 2) return [35, 37, 39, 41]
  const sorted = values.toSorted((first, second) => first - second)
  const percentile = (fraction: number) => sorted[Math.floor((sorted.length - 1) * fraction)]
  const hot = hotspotThreshold ?? percentile(0.75)
  const warm = Math.min(hot - 1, Math.floor(percentile(0.25) * 2) / 2)
  const warmer = Math.min(hot - 0.5, Math.max(warm + 0.5, Math.round(percentile(0.5) * 2) / 2))
  const hottest = Math.max(hot + 0.5, Math.round(percentile(0.95) * 2) / 2)
  return [warm, warmer, hot, hottest]
}

export function heatColor(value: number | null, thresholds: [number, number, number, number]) {
  const [warm, warmer, hot, hottest] = thresholds
  if (value === null || !Number.isFinite(value)) return "#9ba8b6"
  if (value >= hottest) return "#9c2542"
  if (value >= hot) return "#db4851"
  if (value >= warmer) return "#ea754e"
  if (value >= warm) return "#f2a358"
  return "#f5cd77"
}
