export const maxBudget = 1_000_000_000

export function formatBudgetInput(value: string) {
  const [whole, fraction] = value.replace(/[.\s]/g, "").split(",")
  const digits = whole.replace(/^0+(?=\d)/, "")
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
  return fraction === undefined ? grouped : `${grouped || "0"},${fraction}`
}

export function parseBudget(value: string) {
  if (!/^\d+(?:\.\d{3})*(?:,\d{0,2})?$/.test(value)) return null
  const amount = Number(value.replaceAll(".", "").replace(",", "."))
  return Number.isFinite(amount) && amount <= maxBudget ? amount : null
}
