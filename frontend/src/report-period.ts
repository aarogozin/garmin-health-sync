/** Count inclusive calendar dates in UTC so daylight-saving changes cannot shorten a period. */
export function reportDays(report: { start_date: string; end_date: string }): number {
  return Math.round((Date.parse(report.end_date) - Date.parse(report.start_date)) / 86_400_000) + 1
}
