

// Saving small things on the phone (as JSON text), so they survive closing the app.
// The real storage is plugged in by the app at start-up; until then (and in tests) it's memory.

export type Store = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

const memory = new Map<string, string>();
let current: Store = {
  getItem: async (key) => memory.get(key) ?? null,
  setItem: async (key, value) => {
    memory.set(key, value);
  },
  removeItem: async (key) => {
    memory.delete(key);
  },
};

// Plug in the phone's storage (AsyncStorage), once, when the app starts
export function setStore(store: Store): void {
  current = store;
}

// Read a saved value, or the fallback if there isn't one (or it can't be read)
export async function load<T>(key: string, fallback: T): Promise<T> {
  const text = await current.getItem(key);
  if (text === null) return fallback;
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

export async function save(key: string, value: unknown): Promise<void> {
  await current.setItem(key, JSON.stringify(value));
}

export async function forget(key: string): Promise<void> {
  await current.removeItem(key);
}
