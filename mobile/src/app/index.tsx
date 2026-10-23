

import { useEffect, useState } from 'react';
import { ActivityIndicator, Button, StyleSheet, Text, View } from 'react-native';

import { getHealth, type Health } from '@/api/client';

// What the screen is showing right now
type State =
  | { kind: 'loading' }
  | { kind: 'connected'; health: Health }
  | { kind: 'failed'; message: string };

// Card 4.1: prove the phone can reach the API on your computer
export default function ConnectionCheck() {
  const [state, setState] = useState<State>({ kind: 'loading' });

  async function check() {
    setState({ kind: 'loading' });
    try {
      setState({ kind: 'connected', health: await getHealth() });
    } catch (error) {
      setState({ kind: 'failed', message: String(error) });
    }
  }

  // Run the check once, when the screen first appears
  useEffect(() => {
    check();
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.greeting}>
        May the Grace of the day greet you on morning rays! Start the day with a smile!
      </Text>

      {state.kind === 'loading' && <ActivityIndicator size="large" />}

      {state.kind === 'connected' && (
        <Text style={styles.ok}>
          Connected to {state.health.app} ({state.health.environment})
        </Text>
      )}

      {state.kind === 'failed' && (
        <>
          <Text style={styles.error}>Can't reach the API: {state.message}</Text>
          <Text style={styles.hint}>API address: {process.env.EXPO_PUBLIC_API_URL ?? 'not set'}</Text>
        </>
      )}

      <Button title="Check again" onPress={check} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  greeting: { fontSize: 18, textAlign: 'center' },
  ok: { fontSize: 16, color: '#1b7a3a' },
  error: { fontSize: 16, color: '#b3261e', textAlign: 'center' },
  hint: { fontSize: 13, color: '#666' },
});
