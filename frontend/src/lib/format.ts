import type { Status } from '../api/types'

export const STATUS_LABELS: Record<Status, string> = {
  concept: 'Concept',
  design: 'Design',
  in_review: 'In Review',
  released: 'Released',
  ordered: 'Ordered',
  in_fabrication: 'In Fabrication',
  assembled: 'Assembled',
  installed: 'Installed',
  needs_rework: 'Needs Rework',
  scrapped: 'Scrapped',
}

export const STATUS_COLORS: Record<Status, string> = {
  concept: '#767d8c',
  design: '#3b82f6',
  in_review: '#8b5cf6',
  released: '#22c55e',
  ordered: '#14b8a6',
  in_fabrication: '#f59e0b',
  assembled: '#84cc16',
  installed: '#22c55e',
  needs_rework: '#ef4444',
  scrapped: '#57606f',
}

export const STATUS_ORDER = Object.keys(STATUS_LABELS) as Status[]

/** Cost is stored as integer cents; forms and displays work in dollars. */
export function centsToDollars(cents: number | null): string {
  return cents == null ? '' : (cents / 100).toFixed(2)
}

export function formatMoney(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function humanSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value < 10 && i > 0 ? value.toFixed(1) : Math.round(value)} ${units[i]}`
}

/** Pull a 4-digit season out of a project name like "Baja 2027 Car". */
export function seasonFromName(name: string): string | null {
  return /\d{4}/.exec(name)?.[0] ?? null
}
