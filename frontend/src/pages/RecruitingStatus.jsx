import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getCachedRecruitingStatus,
  loadRecruitingStatus,
} from '../lib/api/recruitingStatusData'
import NoDataTable from '../components/NoDataTable'

const metricCards = [
  { label: 'Primary Recruiters', key: 'technicalRecruitersCount', tone: 'cyan' },
  { label: 'Active Reqs Today', key: 'activeRequirementsAsOfToday', tone: 'green' },
  { label: 'Active Reqs CF', key: 'activeRequirementsCarriedForwardUpToYesterday', tone: 'amber' },
  { label: 'Recruiters Working', key: 'recruitersWorkingOnRequirementsCount', tone: 'violet' },
  { label: 'Recruiters Idle', key: 'idleRecruitersCount', tone: 'orange' },
  { label: 'Submissions Today', key: 'totalSubmissionsToday', tone: 'cyan' },
]

const toneClass = {
  cyan: 'text-[#00eaff]',
  green: 'text-[#39ffad]',
  amber: 'text-[#ffb000]',
  violet: 'text-[#8d5cff]',
  orange: 'text-[#ff9f0a]',
}

const RECRUITERS_PER_SLIDE = 3
const RECRUITER_SLIDE_MS = 3500
const FADE_MS = 350

function isPersonName(value) {
  const name = String(value || '').trim()
  return (
    name.length > 1 &&
    name.length <= 60 &&
    /[a-z]/i.test(name) &&
    !/[0-9,/\\_=|]/.test(name)
  )
}

function formatRecruiterName(value) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean)

  if (parts.length < 2) return parts[0] || ''

  return `${parts[0]} ${parts[1][0].toUpperCase()}.`
}

function StatusMetric({ metric, value }) {
  return (
    <article className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-5 overflow-hidden rounded-lg border border-white/10 bg-[#071120]/90 p-5 shadow-[0_18px_42px_rgba(0,0,0,0.24)] sm:p-6 2xl:p-7">
      <p className="min-w-0 text-center text-[clamp(30px,2.05vw,46px)] font-black leading-tight text-white">
        {metric.label}
      </p>
      <strong className={`min-w-[1.4em] justify-self-end text-right font-mono text-[clamp(60px,4.4vw,104px)] font-black leading-none ${toneClass[metric.tone]}`}>
        {value ?? 0}
      </strong>
    </article>
  )
}

function NameList({ title, names, emptyText, accentClass }) {
  const displayNames = useMemo(() => names.filter(isPersonName), [names])
  const slides = useMemo(() => {
    const chunks = []

    for (let index = 0; index < displayNames.length; index += RECRUITERS_PER_SLIDE) {
      chunks.push(displayNames.slice(index, index + RECRUITERS_PER_SLIDE))
    }

    return chunks
  }, [displayNames])
  const [activeSlide, setActiveSlide] = useState(0)
  const [isFading, setIsFading] = useState(false)
  const fadeTimerRef = useRef(null)

  useEffect(() => {
    setActiveSlide(0)
    setIsFading(false)
  }, [displayNames])

  useEffect(() => {
    if (slides.length <= 1) return undefined

    const interval = setInterval(() => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
      setIsFading(true)

      fadeTimerRef.current = setTimeout(() => {
        setActiveSlide((slide) => (slide + 1) % slides.length)
        setIsFading(false)
      }, FADE_MS)
    }, RECRUITER_SLIDE_MS)

    return () => {
      clearInterval(interval)
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    }
  }, [slides.length])

  const visibleNames = slides[activeSlide] || []

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-white/10 bg-[#071120]/90 p-4 sm:p-5">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-4">
        <h2 className={`text-[clamp(24px,1.8vw,40px)] font-black leading-tight ${accentClass}`}>{title}</h2>
        <span className="font-mono text-[clamp(30px,2.2vw,46px)] font-black leading-none text-white">{displayNames.length}</span>
      </div>
      {displayNames.length ? (
        <div
          className={`grid min-h-0 flex-1 grid-cols-3 gap-3 overflow-hidden transition-opacity duration-300 ease-in-out ${
            isFading ? 'opacity-0' : 'opacity-100'
          }`}
        >
          {visibleNames.map((name) => (
            <div
              key={name}
              className="flex min-h-0 min-w-0 items-center overflow-hidden rounded-md border border-white/10 bg-white/[0.04] px-5 text-[clamp(26px,1.85vw,40px)] font-black leading-tight text-white"
              title={name}
            >
              <span className="block min-w-0 truncate">{formatRecruiterName(name)}</span>
            </div>
          ))}
          {Array.from({ length: RECRUITERS_PER_SLIDE - visibleNames.length }).map((_, index) => (
            <div key={`empty-${index}`} className="min-w-0" />
          ))}
        </div>
      ) : (
        <p className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] px-4 text-center font-mono text-[clamp(20px,1.5vw,34px)] text-slate-400">
          {emptyText}
        </p>
      )}
    </section>
  )
}

export default function RecruitingStatus() {
  const [hasInitialCache] = useState(() => Boolean(getCachedRecruitingStatus()))
  const [data, setData] = useState(() => getCachedRecruitingStatus())
  const [loading, setLoading] = useState(() => !getCachedRecruitingStatus())
  const [error, setError] = useState(null)

  const loadStatus = useCallback(async ({ force = false, quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    setError(null)

    const cached = getCachedRecruitingStatus()
    if (!force && cached) {
      setData(cached)
      setLoading(false)
      return
    }

    try {
      const status = await loadRecruitingStatus({ force })
      setData(status)
    } catch (err) {
      setError(err.message || 'Failed to load recruiting status')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const preloadDone = (() => {
      try {
        return localStorage.getItem('dashboard-preload-done') === '1'
      } catch {
        return false
      }
    })()

    // If preload already fetched `/dashboard/status`, avoid forcing a 2nd request.
    loadStatus({
      force: !preloadDone,
      quiet: hasInitialCache || preloadDone,
    })
  }, [hasInitialCache, loadStatus])

  const hasRecruitingData = useMemo(() => {
    if (!data) return false

    const hasMetricData = metricCards.some((metric) => Number(data[metric.key]) > 0)
    const hasWorkingRecruiters = (data.recruitersWorkingOnRequirements || []).some(isPersonName)
    const hasIdleRecruiters = (data.idleRecruiters || []).some(isPersonName)

    return hasMetricData || hasWorkingRecruiters || hasIdleRecruiters
  }, [data])

  return (
    <main className="relative h-[calc(100vh-78px)] overflow-hidden bg-[#030914]">
      <div className="executive-grid absolute inset-0" />
      <div className="relative z-10 mx-auto flex h-full w-full max-w-[2560px] flex-col px-4 py-3 sm:px-8 lg:px-10">
        <div className="mb-3 shrink-0">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <h1 className="text-[clamp(42px,4.2vw,86px)] font-black leading-none text-white">
              Recruiting Status
            </h1>
          </div>
        </div>

        {error && (
          <div className="mb-5 rounded-lg border border-red-400/20 bg-red-950/40 px-5 py-4 font-mono text-sm text-red-200">
            {error}
          </div>
        )}

        {!loading && !error && !hasRecruitingData ? (
          <NoDataTable title="No Recruiting Data" />
        ) : (
        <div className="grid min-h-0 flex-1 grid-rows-[1fr_1fr_2fr] gap-4">
          <div className="grid min-h-0 grid-cols-3 gap-4">
            {metricCards.slice(0, 3).map((metric) => (
              <StatusMetric
                key={metric.key}
                metric={metric}
                value={loading ? '...' : data?.[metric.key]}
              />
            ))}
          </div>

          <div className="grid min-h-0 grid-cols-3 gap-4">
            {metricCards.slice(3, 6).map((metric) => (
              <StatusMetric
                key={metric.key}
                metric={metric}
                value={loading ? '...' : data?.[metric.key]}
              />
            ))}
          </div>

          <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-2">
            <NameList
              title="Recruiters Working List"
              names={data?.recruitersWorkingOnRequirements || []}
              emptyText="No recruiters currently assigned to active requirements."
              accentClass="text-[#39ffad]"
            />
            <NameList
              title="Idle Recruiters List"
              names={data?.idleRecruiters || []}
              emptyText="No idle recruiters currently identified."
              accentClass="text-[#ff9f0a]"
            />
          </div>
        </div>
        )}
      </div>
    </main>
  )
}
