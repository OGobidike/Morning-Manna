

import { router } from 'expo-router';
import { Button, StyleSheet, Text, View } from 'react-native';

// Onboarding 1 of 3
export default function Welcome() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Morning Manna</Text>
      <Text style={styles.greeting}>
        May the Grace of the day greet you on morning rays! Start the day with a smile!
      </Text>
      <Text style={styles.body}>One short passage each morning, at the time you wake up.</Text>
      <Button title="Begin" onPress={() => router.push('/wake-time')} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, padding: 32 },
  title: { fontSize: 32, fontWeight: '700' },
  greeting: { fontSize: 18, textAlign: 'center' },
  body: { fontSize: 16, color: '#555', textAlign: 'center' },
});
