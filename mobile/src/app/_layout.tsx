

import { Stack } from 'expo-router';

// The root layout: every screen in src/app/ is shown inside this stack of screens
export default function RootLayout() {
  return <Stack screenOptions={{ title: 'Morning Manna' }} />;
}
