import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const DEFAULTS = {
  organization: "Organization",
  campus: "Campus",
  department: "Department",
  academic_unit: "Academic Unit",
  level: "Level",
  section: "Section",
  subject: "Subject",
  student: "Student",
  faculty: "Faculty",
  exam: "Exam",
  attendance: "Attendance",
};

const CACHE_KEY = "athena.terminology.v1";

let inFlight = null;
let cached = null;
const listeners = new Set();

function notify() {
  for (const l of listeners) l(cached);
}

async function fetchTerms() {
  if (inFlight) return inFlight;
  inFlight = api.get("/settings/terminology")
    .then((r) => {
      cached = { ...DEFAULTS, ...(r.data?.terms || {}) };
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(cached)); } catch {}
      notify();
      return cached;
    })
    .catch(() => {
      cached = { ...DEFAULTS };
      notify();
      return cached;
    })
    .finally(() => { inFlight = null; });
  return inFlight;
}

/**
 * Clear the in-memory + localStorage cache and re-fetch from the server.
 * Call this on login / logout / org switch so a new user never sees the previous
 * tenant's terminology map.
 */
export function invalidateTerminology() {
  cached = null;
  try { localStorage.removeItem(CACHE_KEY); } catch {}
  notify();
  return fetchTerms();
}

/** Local-only reset (used on logout — do NOT fetch, no auth). */
export function resetTerminology() {
  cached = { ...DEFAULTS };
  try { localStorage.removeItem(CACHE_KEY); } catch {}
  notify();
}

/**
 * useTerminology — returns:
 *   t(key)      => tenant-renamed label (falls back to default)
 *   plural(key) => t(key) + "s" (simple pluralisation)
 *   refresh()   => refetch from server
 *   terms       => the whole map
 */
export default function useTerminology() {
  const [terms, setTerms] = useState(() => {
    if (cached) return cached;
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) return { ...DEFAULTS, ...(JSON.parse(raw) || {}) };
    } catch {}
    return DEFAULTS;
  });

  useEffect(() => {
    const listener = (m) => setTerms(m || DEFAULTS);
    listeners.add(listener);
    if (!cached) fetchTerms();
    return () => { listeners.delete(listener); };
  }, []);

  const t = useCallback((key) => terms[key] || DEFAULTS[key] || key, [terms]);
  const plural = useCallback((key) => {
    const word = t(key);
    if (!word) return "";
    if (/s$/i.test(word)) return word;
    // "y" preceded by a consonant → "ies" (Faculty → Faculties)
    if (/[bcdfghjklmnpqrstvwxz]y$/i.test(word)) return word.slice(0, -1) + "ies";
    // words ending in "s","x","z","ch","sh" → add "es"
    if (/(s|x|z|ch|sh)$/i.test(word)) return word + "es";
    return word + "s";
  }, [t]);
  const refresh = useCallback(() => { cached = null; return fetchTerms(); }, []);

  return { t, plural, refresh, terms };
}
