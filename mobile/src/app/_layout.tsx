

import { Link, Stack } from 'expo-router';

import { SessionProvider, useSession } from '@/session';
// Loaded here so the notification handler is set as soon as the app starts
import '@/reminders';

export default function RootLayout() {
  return (
    <SessionProvider>
      <Screens />
    </SessionProvider>
  );
}

// Onboarding screens before sign-up, the main screen after. Expo Router sends the
// reader to whichever group they're allowed in, and back-navigation can't cross over.
function Screens() {
  const { ready, onboarded } = useSession();

  // Show nothing for the moment it takes to read the saved session
  if (!ready) return null;

  return (
    <Stack screenOptions={{ title: 'Morning Manna' }}>
      <Stack.Protected guard={onboarded}>
        <Stack.Screen
          name="index"
          options={{
            title: 'Today',
            headerRight: () => (
              <Link href="/settings" style={{ fontSize: 16, color: '#208AEF' }}>
                Settings
              </Link>
            ),
          }}
        />
        <Stack.Screen name="settings" options={{ title: 'Settings' }} />
      </Stack.Protected>

      <Stack.Protected guard={!onboarded}>
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="wake-time" options={{ title: 'Your wake time' }} />
        <Stack.Screen name="plan" options={{ title: 'Choose a plan' }} />
      </Stack.Protected>
    </Stack>
  );
}
