

// Reading without a connection: a saved copy of the coming passages, and readings finished
// offline that wait on the phone until they can be sent.

import { ApiError, completeReading, openReading, type Passage, type Streak, type Upcoming } from '@/api/client';
import { isoDay } from '@/calendar';
import { forget, load, save } from '@/store';

const SNAPSHOT_KEY = 'morning-manna.snapshot';
const PENDING_KEY = 'morning-manna.pending-readings';

// What the app last saw online
export type Snapshot = { savedAt: string; upcoming: Upcoming; streak: Streak };

// A reading finished offline. reading_id is filled in once the API has opened it.
export type PendingReading = {
  day_number: number;
  opened_at: string;
  completed_at: string;
  reading_id?: number;
};

export function saveSnapshot(snapshot: Snapshot): Promise<void> {
  return save(SNAPSHOT_KEY, snapshot);
}

export function loadSnapshot(): Promise<Snapshot | null> {
  return load<Snapshot | null>(SNAPSHOT_KEY, null);
}

export function loadPending(): Promise<PendingReading[]> {
  return load<PendingReading[]>(PENDING_KEY, []);
}

export async function addPending(reading: PendingReading): Promise<void> {
  const pending = await loadPending();
  pending.push(reading);
  await save(PENDING_KEY, pending);
}

// Forget everything saved for offline (e.g. when the reader starts over)
export async function clearOffline(): Promise<void> {
  await forget(SNAPSHOT_KEY);
  await forget(PENDING_KEY);
}

// The passage to read next while offline: the first saved one not already finished offline
export function nextOfflinePassage(snapshot: Snapshot, pending: PendingReading[]): Passage | null {
  const finished = new Set(pending.map((reading) => reading.day_number));
  return snapshot.upcoming.passages.find((passage) => !finished.has(passage.day_number)) ?? null;
}

// Read today already: before the connection went, or here while offline
export function readToday(snapshot: Snapshot, pending: PendingReading[]): boolean {
  const today = isoDay(new Date());
  return (
    snapshot.streak.last_read_on === today ||
    pending.some((reading) => isoDay(new Date(reading.completed_at)) === today)
  );
}

// Send readings finished offline, oldest first, each with its real times.
// Stops at the first connection problem and keeps the rest for next time.
export async function syncPending(token: string): Promise<number> {
  const pending = await loadPending();
  let sent = 0;
  while (pending.length > 0) {
    const next = pending[0];
    try {
      // Open it once; remember the id, so a retry doesn't open a second one
      if (next.reading_id === undefined) {
        next.reading_id = (await openReading(token, next.opened_at)).id;
        await save(PENDING_KEY, pending);
      }
      await completeReading(token, next.reading_id, next.completed_at);
    } catch (error) {
      // 404 (no plan any more), 409 (plan already finished) or 422 (too old, or a bad time):
      // the API will never accept it, so let it go. Anything else (still offline): try later.
      const refused = error instanceof ApiError && [404, 409, 422].includes(error.status);
      if (!refused) break;
    }
    pending.shift();
    sent += 1;
    await save(PENDING_KEY, pending);
  }
  return sent;
}
