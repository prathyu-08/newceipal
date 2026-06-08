/**
 * recruitingStatusData.js
 * -----------------------
 * FIX 3: Added TTL (10 min) to the localStorage cache.
 *         Previously data was cached with no expiry, causing stale state
 *         to be returned indefinitely after the first load.
 */
import { fetchRecruitingStatus } from './dashboardApi'

const STATUS_CACHE_KEY = 'recruiting-status-cache'
// FIX 3: Define TTL (10 minutes, matching backend status_cache_ttl_seconds)
const STATUS_CACHE_TTL_MS = 10 * 60 * 1000

let memoryCache = null
let memoryCacheAt = 0
let inFlightLoad = null

export function getCachedRecruitingStatus() {
  const now = Date.now()

  // FIX 3: Check in-memory TTL first
  if (memoryCache && now - memoryCacheAt < STATUS_CACHE_TTL_MS) {
    return memoryCache
  }

  try {
    const raw = localStorage.getItem(STATUS_CACHE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw)
    const savedAt = Number(parsed?.savedAt || 0)
    const data = parsed?.data

    // FIX 3: Respect TTL on stored data
    if (!data || !savedAt || now - savedAt > STATUS_CACHE_TTL_MS) return null

    memoryCache = data
    memoryCacheAt = savedAt
    return data
  } catch {
    // Storage can fail in private mode or when data is malformed.
    return null
  }
}

export async function loadRecruitingStatus({ force = false } = {}) {
  if (!force) {
    const cachedStatus = getCachedRecruitingStatus()

    if (cachedStatus) {
      return cachedStatus
    }
  }

  if (inFlightLoad) {
    return inFlightLoad
  }

  inFlightLoad = fetchRecruitingStatus()
    .then((status) => {
      const now = Date.now()
      memoryCache = status
      memoryCacheAt = now

      try {
        // FIX 3: Store with savedAt timestamp so TTL can be enforced on read
        localStorage.setItem(
          STATUS_CACHE_KEY,
          JSON.stringify({ savedAt: now, data: status }),
        )
      } catch {
        // Keep rendering if storage is unavailable.
      }

      return status
    })
    .finally(() => {
      inFlightLoad = null
    })

  return inFlightLoad
}