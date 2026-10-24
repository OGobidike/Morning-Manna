// ── Imports: outside packages first ──────────────────────────────────────────
// Reads the wakeTime that the previous screen passed along
import { useLocalSearchParams } from 'expo-router';
// useState = values the screen remembers; useEffect = run code when the screen appears
import { useEffect, useState } from 'react';
// The building blocks we draw the screen with
import { ActivityIndicator, Button, Pressable, StyleSheet, Text, View } from 'react-native';

// ── Then our own files (the @/ shortcut means src/) ──────────────────────────
// Fetches the list of plans, plus the Plan type describing one plan
import { getPlans, type Plan } from '@/api/client';
// Asks for notification permission, and sets the daily reminder
import { askForReminders, scheduleDailyReminder } from '@/reminders';
// The shared session: lets this screen finish onboarding (sign up + start the plan)
import { useSession } from '@/session';

// Onboarding 3 of 3: pick a plan, then sign up and start it
export default function ChoosePlan() {
  // The wake time chosen on the previous screen, e.g. "06:30"
  const { wakeTime } = useLocalSearchParams<{ wakeTime: string }>();
  // The function that signs up and starts the plan
  const { finishOnboarding } = useSession();

  // ── What this screen remembers ────────────────────────────────────────────
  // The plans from the API (null = still loading)
  const [plans, setPlans] = useState<Plan[] | null>(null);
  // The id of the plan the reader tapped (null = none chosen yet)
  const [chosen, setChosen] = useState<number | null>(null);
  // True while signing up, to show a spinner instead of the button
  const [saving, setSaving] = useState(false);
  // An error message to show, if something went wrong
  const [error, setError] = useState<string | null>(null);

  // Load the plans once, when the screen first appears (the [] means "only once")
  useEffect(() => {
    getPlans()
      .then((loaded) => {
        setPlans(loaded);
        // With only one plan, choose it for the reader
        if (loaded.length === 1) setChosen(loaded[0].id);
      })
      .catch((e) => setError(`Couldn't load plans: ${String(e)}`));
  }, []);

  // Runs when the reader presses "Start my mornings"
  async function start() {
    // Nothing chosen yet: do nothing (the button is disabled anyway)
    if (chosen === null) return;
    setSaving(true);
    setError(null);
    try {
      // Use the chosen wake time, or 06:00 if none came through
      const time = wakeTime ?? '06:00';
      // Ask for reminders first: the prompt explains itself, and saying no is fine
      if (await askForReminders()) await scheduleDailyReminder(time);
      // Once this succeeds, the layout moves the reader to the main screen by itself
      await finishOnboarding(time, chosen);
    } catch (e) {
      // Show what went wrong (e.g. no connection, or too many sign-ups) and let them retry
      setError(`Couldn't start your plan: ${String(e)}`);
      setSaving(false);
    }
  }

  // ── What the screen shows ─────────────────────────────────────────────────
  // Still loading the plans, and no error yet: show a spinner
  if (plans === null && error === null) {
    return <ActivityIndicator style={styles.loading} size="large" />;
  }

  return (
    <View style={styles.container}>
      {/* One tappable card per plan. The chosen one gets a blue border */}
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

      {/* The error message, only if there is one */}
      {error && <Text style={styles.error}>{error}</Text>}

      {/* While signing up: a spinner. Otherwise: the button (greyed out until a plan is chosen) */}
      {saving ? (
        <ActivityIndicator size="large" />
      ) : (
        <Button title="Start my mornings" onPress={start} disabled={chosen === null} />
      )}
    </View>
  );
}

// ── Styles: how each piece looks ─────────────────────────────────────────────
const styles = StyleSheet.create({
  // The spinner fills the screen, so it sits in the middle
  loading: { flex: 1 },
  // The whole page: centred vertically, with space between items
  container: { flex: 1, justifyContent: 'center', gap: 16, padding: 24 },
  // A plan card: grey rounded border
  card: { borderWidth: 2, borderColor: '#ddd', borderRadius: 12, padding: 16, gap: 6 },
  // Added on top of "card" when chosen: blue border, light blue background
  cardChosen: { borderColor: '#208AEF', backgroundColor: '#EAF4FE' },
  // The plan's name
  name: { fontSize: 20, fontWeight: '600' },
  // The plan's description, in a softer grey
  description: { fontSize: 15, color: '#555' },
  // Error text in red, centred
  error: { fontSize: 15, color: '#b3261e', textAlign: 'center' },
});