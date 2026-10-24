

import { Button, StyleSheet, Text, View } from 'react-native';

import { useSession } from '@/session';

// The main screen. Card 4.3 turns this into today's passage.
export default function Home() {
  const { reset } = useSession();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>You're all set</Text>
      <Text style={styles.body}>Your first morning passage is waiting. (It arrives on this screen in Card 4.3.)</Text>

      {/* Only in development: forget this reader, to test onboarding again */}
      {__DEV__ && <Button title="Start over (dev only)" color="#888" onPress={reset} />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, padding: 32 },
  title: { fontSize: 28, fontWeight: '700' },
  body: { fontSize: 16, color: '#555', textAlign: 'center' },
});
