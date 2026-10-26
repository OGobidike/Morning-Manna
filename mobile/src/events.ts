

// Analytics events: recorded as they happen, sent to the API in batches.
// Batching means one request for many events, kinder to the battery and the network.

import { ApiError, type AppEvent, type EventType, sendEvents } from '@/api/client';
import { load, save } from '@/store';
import { clearOffline } from './offline';

// Send as soon as this many are waiting
const BATCH_SIZE = 10;
// The API takes at most 100 per request; if more pile up (say, offline for days), keep the newest
const MAX_WAITING = 100;
// Waiting events are also saved on the phone, so closing the app doesn't lose them
const SAVED_KEY = 'morning-manna.events';

const waiting: AppEvent[] = [];
let token: string | null = null;
let sending = false;
// False until events saved last time have been loaded back in
let restored = false;

function persist(): Promise<void> {
  // Before restoring, saving would overwrite the events from last time
  return restored ? save(SAVED_KEY, waiting) : Promise.resolve();
}

// Load the events saved last time back into the queue. Call once, when the app starts.
export async function restoreEvents(): Promise<void> {
  if (restored) return;
  const saved = await load<AppEvent[]>(SAVED_KEY, []);
  waiting.unshift(...saved);
  if (waiting.length > MAX_WAITING) waiting.splice(0, waiting.length - MAX_WAITING);
  restored = true;
  await persist();
}

// Events can only be sent once the reader has a token; until then they wait
export function setEventsToken(next: string | null): void {
  token = next;
}

// Record that something happened, right now
export function track(type: EventType, properties: Record<string, unknown> = {}): void {
  waiting.push({ event_type: type, occurred_at: new Date().toISOString(), properties });
  if (waiting.length > MAX_WAITING) waiting.splice(0, waiting.length - MAX_WAITING);
  void persist();
  if (waiting.length >= BATCH_SIZE) void flush();
}

// Send everything waiting, in one request. Safe to call at any time.
export async function flush(): Promise<void> {
  if (!token || sending || waiting.length === 0) return;
  sending = true;
  // Events tracked while this request is in flight join the queue behind this batch
  const batch = waiting.slice(0, MAX_WAITING);
  try {
    await sendEvents(token, batch);
    waiting.splice(0, batch.length);
    await persist();
  } catch (error) {
    // 422 means the API will never accept this batch (e.g. a phone clock far in the future),
    // so drop it. Anything else (offline, server down) keeps the events for the next try.
    if (error instanceof ApiError && error.status === 422) {
      waiting.splice(0, batch.length);
      await persist();
    }
  } finally {
    sending = false;
  }
}

// How many events are waiting (for tests and the dev screen)
export function waitingCount(): number {
  return waiting.length;
}
