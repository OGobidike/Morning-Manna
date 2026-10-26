import AsyncStorage from '@react-native-async-storage/async-storage';
import { DarkTheme, DefaultTheme, Link, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import { AppearanceProvider, palettes, useAppearance } from '@/appearance';
import { flush, restoreEvents, setEventsToken, track } from '@/events';
import { onReminderTapped } from '@/reminders';
import { SessionProvider, useSession } from '@/session';
import { setStore } from '@/store';

// Saved data (offline passages, waiting events) lives in the phone's storage
setStore(AsyncStorage);

export default function RootLayout() {
  return (
    <SessionProvider>
      <AppearanceProvider>
        <Screens />
      </AppearanceProvider>
    </SessionProvider>
  );
}

// Analytics: app opens, reminder taps, and sending the batch when the app is put away
function useEventTracking() {
  const { token, onboarded } = useSession();

  // Events can only be sent with a token
  useEffect(() => {
    setEventsToken(token);
  }, [token]);

  useEffect(() => {
    if (!onboarded) return;
    // Opening the app, now and every time it comes back to the front.
    // First load back any events saved last time, so they're sent too.
    void restoreEvents().then(() => {
      track('app_opened');
      void flush();
    });
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') track('app_opened');
      // Going to the background is the moment to send: the reader is done for now
      if (state === 'background') void flush();
    });
    return () => subscription.remove();
  }, [onboarded]);

  // Tapping the morning reminder
  useEffect(() => onReminderTapped(() => track('notification_opened')), []);
}

// Onboarding screens before sign-up, the main screen after. Expo Router sends the
// reader to whichever group they're allowed in, and back-navigation can't cross over.
function Screens() {
  const { ready, onboarded } = useSession();
  const appearance = useAppearance();
  useEventTracking();

  // Show nothing for the moment it takes to read the saved session
  if (!ready) return null;

  // Onboarding always uses the light look; the reader's choice applies once they're set up
  const theme = onboarded ? appearance.theme : 'light';
  const colors = palettes[theme];
  const base = theme === 'dark' ? DarkTheme : DefaultTheme;

  // Header and screen backgrounds follow our own colours
  const navigationTheme = {
    ...base,
    colors: {
      ...base.colors,
      primary: colors.accent,
      background: colors.background,
      card: colors.background,
      text: colors.text,
      border: colors.border,
    },
  };

  return (
    <ThemeProvider value={navigationTheme}>
      <StatusBar style={theme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ title: 'Morning Manna' }}>
        <Stack.Protected guard={onboarded}>
          <Stack.Screen
            name="index"
            options={{
              title: 'Today',
              headerRight: () => (
                <Link href="/settings" style={{ fontSize: 16, color: colors.accent }}>
                  Settings
                </Link>
              ),
            }}
          />
          <Stack.Screen name="settings" options={{ title: 'Settings' }} />
          <Stack.Screen name="history" options={{ title: 'History' }} />
        </Stack.Protected>

        <Stack.Protected guard={!onboarded}>
          <Stack.Screen name="welcome" options={{ headerShown: false }} />
          <Stack.Screen name="wake-time" options={{ title: 'Your wake time' }} />
          <Stack.Screen name="plan" options={{ title: 'Choose a plan' }} />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}
