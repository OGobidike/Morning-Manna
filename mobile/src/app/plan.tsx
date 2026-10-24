

import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Button, Pressable, StyleSheet, Text, View } from 'react-native';

import { getPlans, type Plan } from '@/api/client';
import { useSession } from '@/session';

// Onboarding 3 of 3: pick a plan, then sign up and start it
export default function ChoosePlan() {
  const { wakeTime } = useLocalSearchParams<{ wakeTime: string }>();
  const { finishOnboarding } = useSession();

  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPlans()
      .then((loaded) => {
        setPlans(loaded);
        // With only one plan, choose it for the reader
        if (loaded.length === 1) setChosen(loaded[0].id);
      })
      .catch((e) => setError(`Couldn't load plans: ${String(e)}`));
  }, []);

  async function start() {
    if (chosen === null) return;
    setSaving(true);
    setError(null);
    try {
      // Once this succeeds, the layout moves the reader to the main screen by itself
      await finishOnboarding(wakeTime ?? '06:00', chosen);
    } catch (e) {
      setError(`Couldn't start your plan: ${String(e)}`);
      setSaving(false);
    }
  }

  if (plans === null && error === null) {
    return <ActivityIndicator style={styles.loading} size="large" />;
  }

  return (
    <View style={styles.container}>
      {plans?.map((plan) => (
        <Pressable
          key={plan.id}
          onPress={() => setChosen(plan.id)}
          style={[styles.card, chosen === plan.id && styles.cardChosen]}
        >
          <Text style={styles.name}>{plan.name}</Text>
          <Text style={styles.description}>{plan.description}</Text>
        </Pressable>
      ))}

      {error && <Text style={styles.error}>{error}</Text>}

      {saving ? (
        <ActivityIndicator size="large" />
      ) : (
        <Button title="Start my mornings" onPress={start} disabled={chosen === null} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1 },
  container: { flex: 1, justifyContent: 'center', gap: 16, padding: 24 },
  card: { borderWidth: 2, borderColor: '#ddd', borderRadius: 12, padding: 16, gap: 6 },
  cardChosen: { borderColor: '#208AEF', backgroundColor: '#EAF4FE' },
  name: { fontSize: 20, fontWeight: '600' },
  description: { fontSize: 15, color: '#555' },
  error: { fontSize: 15, color: '#b3261e', textAlign: 'center' },
});
