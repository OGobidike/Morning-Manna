import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Button,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  ApiError,
  completeReading,
  getMe,
  getStreak,
  getToday,
  openReading,
  type Streak,
  type Today,
} from '@/api/client';
import { askForReminders, remindersAllowed, scheduleDailyReminder, sendTestReminder } from '@/reminders';
import { useSession } from '@/session';

// Today's date on this phone, e.g. "2026-10-24" (the same form as the API's last_read_on)
function localDate(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

type Loaded = { today: Today; streak: Streak; wakeTime: string; reminders: boolean };

// The main screen: today's passage, Mark as read, and the streak
export default function TodayScreen() {
  const { token, reset } = useSession();

  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [readingId, setReadingId] = useState<number | null>(null);
  const [marking, setMarking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      // Ask for all three at once, then wait for all three
      const [today, streak, me] = await Promise.all([getToday(token), getStreak(token), getMe(token)]);

      // Keep the daily reminder in step with the wake time saved on the server.
      // A reminder problem must never hide the passage, so it gets its own try.
      let reminders = false;
      try {
        reminders = await remindersAllowed();
        if (reminders) await scheduleDailyReminder(me.wake_time);
      } catch {
        reminders = false;
      }

      setData({ today, streak, wakeTime: me.wake_time.slice(0, 5), reminders });

      // Start a reading as soon as an unread passage is on screen, so opened_at is honest
      const doneToday = streak.last_read_on === localDate();
      if (!today.completed && !doneToday) {
        setReadingId((await openReading(token)).id);
      }
    } catch (e) {
      setError(e as Error);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function turnOnReminders() {
    if (data && (await askForReminders())) {
      await scheduleDailyReminder(data.wakeTime);
      setData({ ...data, reminders: true });
    }
  }

  async function markAsRead() {
    if (!token) return;
    setMarking(true);
    try {
      // If opening failed earlier, open now so there's something to complete
      const id = readingId ?? (await openReading(token)).id;
      await completeReading(token, id);
      setReadingId(null);
      await load();
    } catch (e) {
      setError(e as Error);
    } finally {
      setMarking(false);
    }
  }

  // 401 (token no longer known) or 404 (no plan): the reader needs setting up again
  if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
    return (
      <View style={styles.centred}>
        <Text style={styles.message}>We couldn't find your reading plan.</Text>
        <Button title="Set up again" onPress={reset} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centred}>
        <Text style={styles.error}>Something went wrong: {error.message}</Text>
        <Button title="Try again" onPress={load} />
      </View>
    );
  }

  if (!data) {
    return <ActivityIndicator style={styles.centred} size="large" />;
  }

  const { today, streak, wakeTime, reminders } = data;
  const doneToday = streak.last_read_on === localDate();

  return (
    <ScrollView
      contentContainerStyle={styles.page}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Text style={styles.streak}>
        {streak.current > 0
          ? `🔥 ${streak.current}-day streak`
          : 'Read today to start your streak'}
      </Text>

      {today.completed ? (
        <View style={styles.card}>
          <Text style={styles.title}>You finished {today.plan_name}! 🎉</Text>
          <Text style={styles.message}>Longest streak: {streak.longest} days</Text>
        </View>
      ) : doneToday ? (
        <View style={styles.card}>
          <Text style={styles.title}>Done for today 🙏</Text>
          <Text style={styles.message}>
            Tomorrow: {today.reference} (day {today.day_number} of {today.total_days})
          </Text>
        </View>
      ) : (
        <>
          <Text style={styles.day}>
            {today.plan_name} · Day {today.day_number} of {today.total_days}
          </Text>
          <Text style={styles.title}>{today.reference}</Text>

          <Text style={styles.passage}>
            {today.verses.map((v) => (
              <Text key={`${v.chapter}:${v.verse}`}>
                <Text style={styles.verseNumber}>{v.verse} </Text>
                {v.text}{' '}
              </Text>
            ))}
          </Text>

          {marking ? (
            <ActivityIndicator size="large" />
          ) : (
            <Button title="Mark as read" onPress={markAsRead} />
          )}
        </>
      )}

      <View style={styles.reminder}>
        {reminders ? (
          <Text style={styles.message}>⏰ Reminder every morning at {wakeTime}</Text>
        ) : (
          <>
            <Text style={styles.message}>Morning reminders are off</Text>
            <Button title="Turn on reminders" onPress={turnOnReminders} />
          </>
        )}
        <Text style={styles.note}>A notification with sound, not an alarm clock.</Text>
      </View>

      {/* Only in development */}
      {__DEV__ && (
        <>
          <Button title="Test reminder in 10 s (dev only)" color="#888" onPress={() => sendTestReminder()} />
          <Button title="Start over (dev only)" color="#888" onPress={reset} />
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centred: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 32 },
  page: { padding: 24, gap: 20 },
  streak: { fontSize: 18, fontWeight: '600', textAlign: 'center' },
  card: { borderRadius: 12, backgroundColor: '#F4F1EA', padding: 24, gap: 10, alignItems: 'center' },
  day: { fontSize: 14, color: '#777', textTransform: 'uppercase', letterSpacing: 1 },
  title: { fontSize: 26, fontWeight: '700', textAlign: 'center' },
  passage: { fontSize: 21, lineHeight: 34 },
  verseNumber: { fontSize: 13, fontWeight: '700', color: '#999' },
  message: { fontSize: 16, color: '#555', textAlign: 'center' },
  error: { fontSize: 16, color: '#b3261e', textAlign: 'center' },
  reminder: { alignItems: 'center', gap: 8, paddingTop: 8 },
  note: { fontSize: 13, color: '#888', textAlign: 'center' },
});