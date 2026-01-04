import dayjs from 'dayjs'

export function formatDate(date: string | Date, format = 'YYYY-MM-DD'): string {
  return dayjs(date).format(format)
}

export function formatDateTime(date: string | Date): string {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

export function getDateRange(range: '7d' | '30d' | '90d'): { startDate: string; endDate: string } {
  const endDate = dayjs().format('YYYY-MM-DD')
  let startDate: string

  switch (range) {
    case '7d':
      startDate = dayjs().subtract(6, 'day').format('YYYY-MM-DD')
      break
    case '30d':
      startDate = dayjs().subtract(29, 'day').format('YYYY-MM-DD')
      break
    case '90d':
      startDate = dayjs().subtract(89, 'day').format('YYYY-MM-DD')
      break
  }

  return { startDate, endDate }
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${Math.round(minutes)}分钟`
  }
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return mins > 0 ? `${hours}小时${mins}分钟` : `${hours}小时`
}

export function formatSleepTime(isoTime: string | null): string {
  if (!isoTime) return '-'
  return dayjs(isoTime).format('HH:mm')
}
