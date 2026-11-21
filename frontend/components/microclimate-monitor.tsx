"use client"

import { ChevronDown, Thermometer } from "lucide-react"
import { useState } from "react"
import type { FormEvent } from "react"
import styles from "./microclimate-monitor.module.css"

const formatter = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2, signDisplay: "exceptZero" })

export function MicroclimateMonitor() {
  const [result, setResult] = useState<number | null>(null)

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const [siteBefore, siteAfter, controlBefore, controlAfter] = [
      "site-before", "site-after", "control-before", "control-after",
    ].map((field) => Number(data.get(field)))
    const difference = siteAfter - siteBefore - (controlAfter - controlBefore)
    setResult(Math.round(difference * 100) / 100)
  }

  return (
    <details className={`panel ${styles.monitor}`}>
      <summary className={styles.summary}>
        <Thermometer size={20} aria-hidden="true" />
        <span>Αποτίμηση μικροκλίματος μετά την παρέμβαση</span>
        <ChevronDown size={18} className={styles.chevron} aria-hidden="true" />
      </summary>
      <div className={styles.content}>
        <p id="monitor-guidance">
          Συμπλήρωσε μέσες θερμοκρασίες αέρα από την ίδια ώρα και το ίδιο ύψος μέτρησης,
          σε συγκρίσιμες ημέρες. Χρησιμοποίησε κοντινό σημείο αναφοράς χωρίς παρέμβαση.
        </p>
        <form onSubmit={calculate} onChange={() => setResult(null)} aria-describedby="monitor-guidance">
          <div className={styles.fields}>
            <fieldset>
              <legend>Στη θέση παρέμβασης</legend>
              <label>Πριν (°C)<input name="site-before" type="number" inputMode="decimal" step="0.01" required /></label>
              <label>Μετά (°C)<input name="site-after" type="number" inputMode="decimal" step="0.01" required /></label>
            </fieldset>
            <fieldset>
              <legend>Στο σημείο αναφοράς</legend>
              <label>Πριν (°C)<input name="control-before" type="number" inputMode="decimal" step="0.01" required /></label>
              <label>Μετά (°C)<input name="control-after" type="number" inputMode="decimal" step="0.01" required /></label>
            </fieldset>
          </div>
          <button className={`outline-button ${styles.submit}`} type="submit">Σύγκρινε τις μετρήσεις</button>
        </form>
        {result !== null && (
          <p className={styles.result} role="status">
            Μεταβολή στη θέση παρέμβασης σε σχέση με το σημείο αναφοράς
            <strong>{formatter.format(result)} °C</strong>
          </p>
        )}
        <p className={styles.method}>
          Η σύγκριση αφαιρεί τη μεταβολή στο σημείο αναφοράς από τη μεταβολή στη θέση παρέμβασης.
          Η επανάληψη σε περισσότερες ημέρες βοηθά στην αποτίμηση του αποτελέσματος.
        </p>
      </div>
    </details>
  )
}
