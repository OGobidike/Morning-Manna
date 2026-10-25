

// Clock times as the app and the API pass them around: "06:30".

// A Date's hours and minutes as "06:30"
export function toHHMM(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// "06:30" (or "06:30:00") as a Date today at that time, for the time picker
export function dateAt(hhmm: string): Date {
  const [hour, minute] = hhmm.split(':').map(Number);
  const date = new Date();
  date.setHours(hour, minute, 0, 0);
  return date;
}
