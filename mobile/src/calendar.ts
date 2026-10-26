

// Calendar days for the history heat map. Plain dates only: no time of day, no time zones.

// "2026-10-26" as a Date at local midnight (new Date("2026-10-26") would mean UTC midnight)
export function parseDay(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
}

// A Date as "2026-10-26", using the phone's own calendar
export function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// The same date, n days later (or earlier, if n is negative)
export function addDays(date: Date, n: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + n);
  return next;
}

// How many days from start to end, counting both (Math.round irons out clock changes)
export function daysCovered(start: Date, end: Date): number {
  return Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
}

// Weeks from the Monday on or before start, to the week holding end. Each week is
// 7 slots, Monday to Sunday; a slot is null when it falls outside start..end.
export function buildWeeks(start: Date, end: Date): (Date | null)[][] {
  // getDay(): Sunday = 0, Monday = 1 ... so this is how many days back Monday was
  const daysSinceMonday = (start.getDay() + 6) % 7;
  const weeks: (Date | null)[][] = [];
  for (let monday = addDays(start, -daysSinceMonday); monday <= end; monday = addDays(monday, 7)) {
    const week: (Date | null)[] = [];
    for (let i = 0; i < 7; i++) {
      const day = addDays(monday, i);
      week.push(day < start || day > end ? null : day);
    }
    weeks.push(week);
  }
  return weeks;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// The month name to show above a week: on the first week, and wherever a month begins
export function monthLabel(week: (Date | null)[], isFirstWeek: boolean): string {
  const days = week.filter((day): day is Date => day !== null);
  const firstOfMonth = days.find((day) => day.getDate() === 1);
  if (firstOfMonth) return MONTHS[firstOfMonth.getMonth()];
  if (isFirstWeek && days.length > 0) return MONTHS[days[0].getMonth()];
  return '';
}
