"use client"

import { Copy, ExternalLink, FileText } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { api } from "../lib/api"
import type { Plan } from "../lib/api"
import styles from "./ai-brief.module.css"

type Brief = Awaited<ReturnType<typeof api.aiBrief>>

export function AiBrief({ plan, isStale }: { plan: Plan | null; isStale: boolean }) {
  const heading = useId()
  const currentPlan = !isStale && plan?.selected.length ? plan : null

  return (
    <section id="city-brief" className={`panel ${styles.panel}`} aria-labelledby={heading}>
      <h2 className={styles.heading} id={heading}><FileText size={22} aria-hidden="true" /> Σύνοψη για τον Δήμο</h2>
      {currentPlan ? (
        <BriefActions key={planKey(currentPlan)} plan={currentPlan} />
      ) : (
        <p className={styles.hint}>
          {isStale ? "Ενημέρωσε το πλάνο για να δημιουργήσεις τη σύνοψη." : "Υπολόγισε ένα πλάνο με παρεμβάσεις για να δημιουργήσεις τη σύνοψη."}
        </p>
      )}
    </section>
  )
}

function planKey(plan: Plan) {
  return JSON.stringify([
    plan.dataset_version, plan.budget_eur, plan.include_inspection, plan.strategy, plan.priority_only, plan.total_cost_eur,
    plan.selected.map(({ id }) => id),
  ])
}

function briefOrigin(brief: Brief) {
  if (brief.source === "hosted_model") {
    return brief.model ? `Ιεράρχηση με μοντέλο AI · ${brief.model}` : "Ιεράρχηση με μοντέλο AI"
  }
  return "Σύνοψη από τα στοιχεία του πλάνου"
}

function evidenceLink(value: string) {
  try {
    const url = new URL(value)
    if (url.protocol === "https:" && !url.username && !url.password) return url.href
  } catch {
    return null
  }
  return null
}

function BriefActions({ plan }: { plan: Plan }) {
  const [brief, setBrief] = useState<Brief | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [copyStatus, setCopyStatus] = useState("")
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => pending.current?.abort(), [])

  async function generate() {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setBusy(true)
    setError(false)
    setCopyStatus("")
    try {
      const response = await api.aiBrief({
        budget_eur: plan.budget_eur,
        priority_only: plan.priority_only,
        include_inspection: plan.include_inspection,
        strategy: plan.strategy,
      }, controller.signal)
      if (!controller.signal.aborted) setBrief(response)
    } catch {
      if (!controller.signal.aborted) setError(true)
    } finally {
      if (pending.current === controller) pending.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  async function copy() {
    if (!brief) return
    const sections = ["Σύνοψη για τον Δήμο", briefOrigin(brief), brief.summary]
    if (brief.priorities.length) sections.push(["Προτεραιότητες", ...brief.priorities.map((item) => `• ${item}`)].join("\n"))
    if (brief.next_step) sections.push(`Επόμενο βήμα\n${brief.next_step}`)
    if (brief.evidence.length) {
      sections.push(["Πηγές", ...brief.evidence.map(({ title, url }) => {
        const link = evidenceLink(url)
        return link ? `${title} · ${link}` : title
      })].join("\n"))
    }
    try {
      await navigator.clipboard.writeText(sections.join("\n\n"))
      setCopyStatus("Η σύνοψη αντιγράφηκε.")
    } catch {
      setCopyStatus("Μπορείς να επιλέξεις και να αντιγράψεις το κείμενο της σύνοψης.")
    }
  }

  return (
    <>
      <div className={styles.actions}>
        <button className={`primary-button ${styles.action}`} type="button" disabled={busy} onClick={() => void generate()}>
          {busy ? "Σύνταξη σύνοψης…" : brief ? "Ενημέρωσε τη σύνοψη" : "Δημιούργησε σύνοψη"}
        </button>
        {brief && (
          <button className={`outline-button ${styles.action}`} type="button" disabled={busy} onClick={() => void copy()}>
            <Copy size={15} aria-hidden="true" /> Αντιγραφή σύνοψης
          </button>
        )}
        {copyStatus && <p className={styles.status} role="status">{copyStatus}</p>}
      </div>
      {error && <p className={styles.error} role="alert">Η σύνοψη δεν δημιουργήθηκε. Δοκίμασε ξανά.</p>}
      <div aria-live="polite" aria-busy={busy}>
        {brief && (
          <div className={styles.result}>
            <p className={styles.origin}>{briefOrigin(brief)}</p>
            {brief.availability === "not_configured" && <p className={styles.hint}>Η διαδικτυακή ιεράρχηση AI ενεργοποιείται από τον διαχειριστή του AthensShade.</p>}
            {brief.availability === "provider_unavailable" && <p className={styles.hint}>Η διαδικτυακή ιεράρχηση AI είναι προσωρινά μη διαθέσιμη.</p>}
            <p className={styles.summary}>{brief.summary}</p>
            {brief.priorities.length > 0 && (
              <>
                <h3>Προτεραιότητες</h3>
                <ul className={styles.priorities}>{brief.priorities.map((item, index) => <li key={index}>{item}</li>)}</ul>
              </>
            )}
            {brief.next_step && (
              <>
                <h3>Επόμενο βήμα</h3>
                <p>{brief.next_step}</p>
              </>
            )}
            {brief.evidence.length > 0 && (
              <>
                <h3>Πηγές</h3>
                <ul className={styles.sources}>
                  {brief.evidence.map(({ title, url }, index) => {
                    const link = evidenceLink(url)
                    return (
                      <li key={index}>
                        {link ? <a href={link} target="_blank" rel="noreferrer">{title} <ExternalLink size={12} aria-hidden="true" /></a> : title}
                      </li>
                    )
                  })}
                </ul>
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}
