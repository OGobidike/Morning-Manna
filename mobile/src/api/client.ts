

// One place for talking to the Morning Manna API.

// Set in mobile/.env, e.g. EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
const API_URL = process.env.EXPO_PUBLIC_API_URL;

// An error the API sent back on purpose, e.g. 404 "start a plan first"
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  token?: string;
};

// Give up on a request with no answer after this long. Android's own networking waits
// forever, so without this a bad signal (or a stopped server) means an endless spinner.
const TIMEOUT_MS = 10_000;

// Call the API and return its JSON, typed as T. Throws ApiError for 4xx/5xx answers.
export async function api<T>(path: string, { method = 'GET', body, token }: Options = {}): Promise<T> {
  if (!API_URL) {
    throw new Error('EXPO_PUBLIC_API_URL is not set: copy mobile/.env.example to mobile/.env');
  }

  // The controller cancels the request if the timer goes off first
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    // Not an ApiError, so screens treat it like being offline
    if (controller.signal.aborted) throw new Error(`No answer from the server after ${TIMEOUT_MS / 1000} s`);
    throw error;
  } finally {
    clearTimeout(timer);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI puts the reason in "detail"
    const detail = typeof data?.detail === 'string' ? data.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

// GET /health, the same answer as `curl localhost:8000/health`
export type Health = { status: string; app: string; environment: string };

export function getHealth(): Promise<Health> {
  return api<Health>('/health');
}

// GET /plans
export type Plan = { id: number; name: string; description: string };

export function getPlans(): Promise<Plan[]> {
  return api<Plan[]>('/plans');
}

// POST /users: the token comes back once, so it must be saved straight away
export type SignUpDetails = { device_id: string; timezone: string; wake_time: string };
export type SignedUp = { id: number; timezone: string; wake_time: string; token: string };

export function signUp(details: SignUpDetails): Promise<SignedUp> {
  return api<SignedUp>('/users', { method: 'POST', body: details });
}

// POST /users/me/plans
export type Enrolment = { id: number; plan_id: number; start_date: string; current_day: number };

export function startPlan(token: string, planId: number): Promise<Enrolment> {
  return api<Enrolment>('/users/me/plans', { method: 'POST', token, body: { plan_id: planId } });
}

// GET /today: this morning's passage (or completed: true once the plan is finished)
export type Verse = { chapter: number; verse: number; text: string };
export type Today = {
  plan_name: string;
  day_number: number;
  total_days: number;
  completed: boolean;
  reference: string | null;
  verses: Verse[];
};

export function getToday(token: string): Promise<Today> {
  return api<Today>('/today', { token });
}

// POST /readings, then POST /readings/{id}/complete
export type Reading = { id: number; plan_day_id: number; opened_at: string; completed_at: string | null };

// openedAt / completedAt: when it really happened, if earlier (a reading saved offline).
// Leave them out to mean "now".
export function openReading(token: string, openedAt?: string): Promise<Reading> {
  const body = openedAt ? { opened_at: openedAt } : undefined;
  return api<Reading>('/readings', { method: 'POST', token, body });
}

export function completeReading(token: string, readingId: number, completedAt?: string): Promise<Reading> {
  const body = completedAt ? { completed_at: completedAt } : undefined;
  return api<Reading>(`/readings/${readingId}/complete`, { method: 'POST', token, body });
}

// GET /users/me/streak
export type Streak = { current: number; longest: number; last_read_on: string | null };

export function getStreak(token: string): Promise<Streak> {
  return api<Streak>('/users/me/streak', { token });
}

// GET /users/me: the reader's settings, e.g. wake_time "06:30:00", translation "KJV"
export type Me = { id: number; timezone: string; wake_time: string; translation: string };

export function getMe(token: string): Promise<Me> {
  return api<Me>('/users/me', { token });
}

// PATCH /users/me: send only what changes, e.g. { wake_time: "05:45" }
export type SettingsChange = Partial<Pick<Me, 'timezone' | 'wake_time' | 'translation'>>;

export function updateMe(token: string, changes: SettingsChange): Promise<Me> {
  return api<Me>('/users/me', { method: 'PATCH', token, body: changes });
}

// GET /translations
export type Translation = { code: string; name: string };

export function getTranslations(): Promise<Translation[]> {
  return api<Translation[]>('/translations');
}


// GET /users/me/history: the days the reader finished a reading, oldest first
export type History = { start: string; end: string; days: string[] };

export function getHistory(token: string, days = 91): Promise<History> {
  return api<History>(`/users/me/history?days=${days}`, { token });
}


// POST /events: app events, sent in batches (the API accepts these types only)
export type EventType =
  | 'app_opened'
  | 'notification_opened'
  | 'reading_opened'
  | 'reading_completed'
  | 'reminder_snoozed';

export type AppEvent = {
  event_type: EventType;
  occurred_at: string;
  properties: Record<string, unknown>;
};

export function sendEvents(token: string, events: AppEvent[]): Promise<{ accepted: number }> {
  return api<{ accepted: number }>('/events', { method: 'POST', token, body: { events } });
}

// GET /today/upcoming: this morning's passage and the next few, to keep for reading offline
export type Passage = { day_number: number; reference: string; verses: Verse[] };
export type Upcoming = { plan_name: string; total_days: number; passages: Passage[] };

export function getUpcoming(token: string, days = 7): Promise<Upcoming> {
  return api<Upcoming>(`/today/upcoming?days=${days}`, { token });
}
