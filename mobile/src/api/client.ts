

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

// Call the API and return its JSON, typed as T. Throws ApiError for 4xx/5xx answers.
export async function api<T>(path: string, { method = 'GET', body, token }: Options = {}): Promise<T> {
  if (!API_URL) {
    throw new Error('EXPO_PUBLIC_API_URL is not set: copy mobile/.env.example to mobile/.env');
  }

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

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

export function openReading(token: string): Promise<Reading> {
  return api<Reading>('/readings', { method: 'POST', token });
}

export function completeReading(token: string, readingId: number): Promise<Reading> {
  return api<Reading>(`/readings/${readingId}/complete`, { method: 'POST', token });
}

// GET /users/me/streak
export type Streak = { current: number; longest: number; last_read_on: string | null };

export function getStreak(token: string): Promise<Streak> {
  return api<Streak>('/users/me/streak', { token });
}
