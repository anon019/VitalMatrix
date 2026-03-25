function padNumber(value) {
  return String(value).padStart(2, '0')
}

function cloneDate(date) {
  return new Date(date.getTime())
}

function addDays(date, days) {
  const nextDate = cloneDate(date)
  nextDate.setDate(nextDate.getDate() + days)
  return nextDate
}

function formatLocalDate(date = new Date()) {
  const targetDate = date instanceof Date ? date : new Date(date)

  return `${targetDate.getFullYear()}-${padNumber(targetDate.getMonth() + 1)}-${padNumber(targetDate.getDate())}`
}

function getRecentLocalDates(days, endDate = new Date()) {
  const dates = []

  for (let i = days - 1; i >= 0; i--) {
    dates.push(formatLocalDate(addDays(endDate, -i)))
  }

  return dates
}

function getMonday(date = new Date()) {
  const monday = cloneDate(date)
  const day = monday.getDay()
  const diff = day === 0 ? -6 : 1 - day

  monday.setDate(monday.getDate() + diff)
  return monday
}

module.exports = {
  addDays,
  formatLocalDate,
  getRecentLocalDates,
  getMonday
}
