

import { Stack } from 'expo-router';

import { SessionProvider, useSession } from '@/session';

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
        <Stack.Screen name="index" />
      </Stack.Protected>

      <Stack.Protected guard={!onboarded}>
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="wake-time" options={{ title: 'Your wake time' }} />
        <Stack.Screen name="plan" options={{ title: 'Choose a plan' }} />
      </Stack.Protected>
    </Stack>
  );
}
