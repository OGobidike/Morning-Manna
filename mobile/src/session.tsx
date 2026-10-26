

// Who the reader is on this phone: their token, and whether they've finished onboarding.

import * as Crypto from 'expo-crypto';
import * as Localization from 'expo-localization';
import * as SecureStore from 'expo-secure-store';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

import { ApiError, signUp, startPlan } from '@/api/client';
import { clearOffline } from '@/offline';

// Secure storage keys (letters, digits, dots, dashes and underscores only)
const TOKEN_KEY = 'morning-manna.token';
const ONBOARDED_KEY = 'morning-manna.onboarded';

type Session = {
  // False until the saved session has been read from storage
  ready: boolean;
  token: string | null;
  onboarded: boolean;
  // Sign up (if not already) and start the chosen plan
  finishOnboarding: (wakeTime: string, planId: number) => Promise<void>;
  // Forget this phone's reader (for testing onboarding again)
  reset: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

// The phone's time zone, e.g. "Africa/Lagos"
function deviceTimeZone(): string {
  return Localization.getCalendars()[0]?.timeZone ?? 'UTC';
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [onboarded, setOnboarded] = useState(false);

  // Read the saved session once, when the app starts
  useEffect(() => {
    (async () => {
      setToken(await SecureStore.getItemAsync(TOKEN_KEY));
      setOnboarded((await SecureStore.getItemAsync(ONBOARDED_KEY)) === 'yes');
      setReady(true);
    })();
  }, []);

  async function finishOnboarding(wakeTime: string, planId: number) {
    let current = token;
    if (!current) {
      const result = await signUp({
        device_id: Crypto.randomUUID(),
        timezone: deviceTimeZone(),
        wake_time: wakeTime,
      });
      current = result.token;
      // Save at once: the API never shows this token again
      await SecureStore.setItemAsync(TOKEN_KEY, current);
      setToken(current);
    }

    try {
      await startPlan(current, planId);
    } catch (error) {
      // 409 means this reader already started the plan, which is fine
      if (!(error instanceof ApiError && error.status === 409)) throw error;
    }

    await SecureStore.setItemAsync(ONBOARDED_KEY, 'yes');
    setOnboarded(true);
  }

  async function reset() {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(ONBOARDED_KEY);
    // The saved passages and offline readings belonged to the old reader
    await clearOffline();
    setToken(null);
    setOnboarded(false);
  }

  return (
    <SessionContext.Provider value={{ ready, token, onboarded, finishOnboarding, reset }}>
      {children}
    </SessionContext.Provider>
  );
}

// Use the session in any screen
export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside <SessionProvider>');
  return session;
}
