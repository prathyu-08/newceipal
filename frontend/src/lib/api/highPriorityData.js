/**
 * highPriorityData.js
 * -------------------
 * FIX 1: getLoadKey now includes `route` in the key so that two calls with
 *         the same date range but different routes do NOT share an in-flight
 *         slot and cause duplicate requests.
 */
import { fetchHighPriorityRequirements } from './dashboardApi'
import {
  readHighPriorityCache,
  writeHighPriorityCache,
} from './dashboardCache'

const memoryCache = new Map()
const inFlightLoads = new Map()

function getCacheKey(dateFrom, dateTo) {
  return `${dateFrom || 'none'}:${dateTo || 'none'}`
}

// FIX 1: route is now part of the load key so different routes don't collide
function getLoadKey(route, dateFrom, dateTo) {
  return `${route || 'high-priority'}:${dateFrom || 'none'}:${dateTo || 'none'}`
}

function fetchRequirements(route, dateFrom, dateTo) {
  // Both routes currently use the same API endpoint.
  // If a separate bdm-wise endpoint is added later, switch here.
  return fetchHighPriorityRequirements({ dateFrom, dateTo })
}

export function getCachedHighPriorityRequirements(dateFrom, dateTo) {
  const cacheKey = getCacheKey(dateFrom, dateTo)
  const memoryRows = memoryCache.get(cacheKey)

  if (Array.isArray(memoryRows)) {
    return memoryRows
  }

  const storedRows = readHighPriorityCache(dateFrom, dateTo)

  if (Array.isArray(storedRows)) {
    memoryCache.set(cacheKey, storedRows)
    return storedRows
  }

  return null
}

export async function loadHighPriorityRequirements({
  dateFrom,
  dateTo,
  force = false,
  route = 'high-priority',
} = {}) {
  const cacheKey = getCacheKey(dateFrom, dateTo)
  const loadKey = getLoadKey(route, dateFrom, dateTo) // FIX 1

  if (!force) {
    const cachedRows = getCachedHighPriorityRequirements(dateFrom, dateTo)

    if (Array.isArray(cachedRows)) {
      return cachedRows
    }
  }

  const inFlightLoad = inFlightLoads.get(loadKey)

  if (inFlightLoad) {
    return inFlightLoad
  }

  const load = fetchRequirements(route, dateFrom, dateTo)
    .then((data) => {
      const rows = Array.isArray(data) ? data : []

      memoryCache.set(cacheKey, rows)
      writeHighPriorityCache(dateFrom, dateTo, rows)

      return rows
    })
    .finally(() => {
      inFlightLoads.delete(loadKey)
    })

  inFlightLoads.set(loadKey, load)

  return load
}