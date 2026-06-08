/**
 * dashboardPreload.js
 * -------------------
 * FIX 2: requestScreenData no longer uses force: true when the preload
 *         has already run. This prevents the same endpoints being hit twice —
 *         once by preloadDashboardData() and again by the page mounting.
 */
import { loadBdmPerformance } from './bdmPerformanceData'
import { loadHighPriorityRequirements } from './highPriorityData'
import { loadRecruitingStatus } from './recruitingStatusData'

const PRELOAD_DONE_KEY = 'dashboard-preload-done'

function getDateRange(offsetDays = 0) {
  const dateValue = new Date()
  dateValue.setDate(dateValue.getDate() + offsetDays)
  const date = dateValue.toISOString().split('T')[0]

  return {
    dateFrom: date,
    dateTo: date,
  }
}

export async function preloadDashboardData() {
  const today = getDateRange()
  const yesterday = getDateRange(-1)

  const loads = Promise.allSettled([
    loadRecruitingStatus({ force: true }),
    loadHighPriorityRequirements({ ...today, force: true, route: 'high-priority' }),
    loadHighPriorityRequirements({ ...yesterday, force: true, route: 'high-priority' }),
    loadBdmPerformance({ period: 'today', force: true }),
  ])

  try {
    localStorage.setItem(PRELOAD_DONE_KEY, String(Date.now()))
  } catch {
    // ignore (private mode / quota)
  }

  return loads
}

/**
 * FIX 2: Check if preload ran recently (within last 15 min).
 * If yes, skip force so we don't re-hit the API immediately.
 */
function wasPreloadedRecently() {
  try {
    const ts = Number(localStorage.getItem(PRELOAD_DONE_KEY) || 0)
    return ts > 0 && Date.now() - ts < 15 * 60 * 1000
  } catch {
    return false
  }
}

export function requestScreenData(screenKey) {
  const today = getDateRange()
  const yesterday = getDateRange(-1)
  // FIX 2: only force if preload hasn't run recently
  const shouldForce = !wasPreloadedRecently()

  switch (screenKey) {
    case 'status':
      return loadRecruitingStatus({ force: shouldForce })
    case 'dashboard':
      return loadHighPriorityRequirements({
        ...today,
        force: shouldForce,
        route: 'high-priority',
      })
    case 'priority':
      return loadHighPriorityRequirements({
        ...yesterday,
        force: shouldForce,
        route: 'high-priority',
      })
    case 'bdm':
      return loadBdmPerformance({ period: 'today', force: shouldForce })
    default:
      return Promise.resolve(null)
  }
}