

import { DarkTheme, DefaultTheme, Link, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { AppearanceProvider, palettes, useAppearance } from '@/appearance';
import { SessionProvider, useSession } from '@/session';
// Loaded here so the notification handler is set as soon as the app starts
import '@/reminders';

export default function RootLayout() {
  return (
    <SessionProvider>
      <AppearanceProvider>
        <Screens />
      </AppearanceProvider>
    </SessionProvider>
  );
}

// Onboarding screens before sign-up, the main screen after. Expo Router sends the
// reader to whichever group they're allowed in, and back-navigation can't cross over.
function Screens() {
  const { ready, onboarded } = useSession();
  const appearance = useAppearance();

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
