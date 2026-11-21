"use client"

import { Search } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { api } from "../lib/api"
import type { EvidenceSearchResponse } from "../lib/api"
import styles from "./evidence-search.module.css"

export function EvidenceSearch() {
  const [query, setQuery] = useState("")
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState<EvidenceSearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const question = query.trim()
    if (question.length < 3) { setError("Γράψε τουλάχιστον 3 χαρακτήρες."); return }
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setPending(true)
    setError(null)
    setResult(null)
    try {
      const response = await api.searchEvidence(question, controller.signal)
      if (!controller.signal.aborted) setResult(response)
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error ? failure.message : "Η αναζήτηση δεν ολοκληρώθηκε.")
      }
    } finally {
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return (
    <section className={styles.search} aria-labelledby="evidence-search-title">
      <h3 id="evidence-search-title">Αναζήτηση τεκμηρίων</h3>
      <form onSubmit={search} className={styles.form} role="search">
        <label htmlFor="evidence-question">Τι θέλεις να τεκμηριώσεις;</label>
        <div className={styles.field}>
          <input
            id="evidence-question"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder="π.χ. Πόσο δροσίζει ένα σκίαστρο;"
            minLength={3}
            maxLength={300}
            required
          />
          <button className="outline-button" type="submit" disabled={pending}>
            <Search size={16} aria-hidden="true" /> {pending ? "Αναζήτηση…" : "Βρες τεκμήρια"}
          </button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
      <div aria-live="polite" aria-busy={pending}>
        {result && (
          <div className={styles.results}>
            <p>{result.method === "semantic" ? "Αναζήτηση με multilingual E5" : "Αναζήτηση με λέξεις-κλειδιά"}</p>
            {result.results.length > 0 ? (
              <ul>
                {result.results.map((item) => (
                  <li key={item.url}>
                    <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                    <p>{item.description}</p>
                  </li>
                ))}
              </ul>
            ) : <p>Δεν βρέθηκε τεκμήριο. Δοκίμασε όρους όπως «δέντρα», «σκίαστρα» ή «απόσβεση».</p>}
          </div>
        )}
      </div>
    </section>
  )
}
