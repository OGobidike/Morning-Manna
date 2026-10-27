

import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
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
  getUpcoming,
  openReading,
  type Passage,
  type Streak,
  type Today,
} from '@/api/client';

import { useAppearance } from '@/appearance';
import { track } from '@/events';
import {
  addPending,
  loadPending,
  loadSnapshot,
  nextOfflinePassage,
  type PendingReading,
  readToday,
  saveLastRead,
  saveSnapshot,
  type Snapshot,
  syncPending,
} from '@/offline';
import { OfflineToday } from '@/offline-today';
import { ReadAgain } from '@/read-again';
import { askForReminders, remindersAllowed, scheduleDailyReminder, sendTestReminder } from '@/reminders';
import { useSession } from '@/session';

// Today's date on this phone, e.g. "2026-10-24" (the same form as the API's last_read_on)
function localDate(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

type Loaded = { today: Today; streak: Streak; wakeTime: string; reminders: boolean };
type Offline = { snapshot: Snapshot; pending: PendingReading[] };

// The main screen: today's passage, Mark as read, and the streak
export default function TodayScreen() {
  const { token, reset } = useSession();
  const { colors, passage } = useAppearance();

  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  // The open reading's id. A ref, not state: changing it doesn't need a redraw,
  // and load() always sees the latest value.
  const readingId = useRef<number | null>(null);
  // When the passage on screen was first shown, for readings saved offline
  const openedAt = useRef<string | null>(null);
  // Set when there's no connection and the saved copy is on screen
  const [offline, setOffline] = useState<Offline | null>(null);
  const [marking, setMarking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      // Send any readings finished offline first, so today's passage and the streak include them
      await syncPending(token);

      // Ask for all four at once, then wait for all four
      const [today, streak, me, upcoming] = await Promise.all([
        getToday(token),
        getStreak(token),
        getMe(token),
        getUpcoming(token),
      ]);
      // Keep a copy of the coming passages, for mornings without a connection
      await saveSnapshot({ savedAt: new Date().toISOString(), upcoming, streak });
      setOffline(null);

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
      if (!today.completed && !doneToday && readingId.current === null) {
        readingId.current = (await openReading(token)).id;
        openedAt.current = new Date().toISOString();
        track('reading_opened', { day_number: today.day_number });
      }
    } catch (e) {
      // An ApiError is the server answering "no". Anything else means it couldn't be
      // reached: show the copy saved on this phone, if there is one.
      const snapshot = e instanceof ApiError ? null : await loadSnapshot();
      if (!snapshot) {
        setError(e as Error);
        return;
      }
      const pending = await loadPending();
      setOffline({ snapshot, pending });
      const next = nextOfflinePassage(snapshot, pending);
      if (next && !readToday(snapshot, pending) && openedAt.current === null) {
        openedAt.current = new Date().toISOString();
        track('reading_opened', { day_number: next.day_number });
      }
    }
  }, [token]);

  // Load every time this screen comes into view, e.g. back from Settings with a new translation
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

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
    if (!token || !data) return;
    setMarking(true);
    // Keep a copy, so the reader can open it again from "Done for today"
    await saveLastRead(data.today);
    try {
      // If opening failed earlier, open now so there's something to complete
      const id = readingId.current ?? (await openReading(token)).id;
      await completeReading(token, id);
      if (data) track('reading_completed', { day_number: data.today.day_number });
      readingId.current = null;
      openedAt.current = null;
      await load();
    } catch (e) {
      // The connection went while reading: keep it on this phone and send it later
      if (!(e instanceof ApiError) && data) {
        await saveOffline(data.today.day_number);
        await load();
      } else {
        setError(e as Error);
      }
    } finally {
      setMarking(false);
    }
  }

  // Mark as read with no connection
  async function markAsReadOffline(passage: Passage) {
    await saveLastRead(passage);
    await saveOffline(passage.day_number);
    if (offline) setOffline({ ...offline, pending: await loadPending() });
  }

  // Save a finished reading on this phone, to be sent by syncPending next time load() works.
  // If the reading was opened on the server before the connection went, finish that one.
  async function saveOffline(dayNumber: number) {
    const now = new Date().toISOString();
    await addPending({
      day_number: dayNumber,
      opened_at: openedAt.current ?? now,
      completed_at: now,
      reading_id: readingId.current ?? undefined,
    });
    track('reading_completed', { day_number: dayNumber });
    readingId.current = null;
    openedAt.current = null;
  }

  // 401 (token no longer known) or 404 (no plan): the reader needs setting up again
  if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
    return (
      <View style={styles.centred}>
        <Text style={[styles.message, { color: colors.muted }]}>We couldn't find your reading plan.</Text>
        <Button title="Set up again" onPress={reset} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centred}>
        <Text style={[styles.error, { color: colors.error }]}>Something went wrong: {error.message}</Text>
        <Button title="Try again" onPress={load} />
      </View>
    );
  }

  if (offline) {
    return (
      <OfflineToday
        snapshot={offline.snapshot}
        pending={offline.pending}
        onMarkRead={markAsReadOffline}
        onRetry={load}
      />
    );
  }

  if (!data) {
    return <ActivityIndicator style={styles.centred} size="large" color={colors.accent} />;
  }

  const { today, streak, wakeTime, reminders } = data;
  const doneToday = streak.last_read_on === localDate();

  return (
    <ScrollView
      contentContainerStyle={styles.page}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Text style={[styles.streak, { color: colors.text }]}>
        {streak.current > 0
          ? `🔥 ${streak.current}-day streak`
          : 'Read today to start your streak'}
      </Text>
      <Link href="/history" style={[styles.link, { color: colors.accent }]}>
        See your history →
      </Link>

      {today.completed ? (
        <View style={[styles.card, { backgroundColor: colors.card }]}>
          <Text style={[styles.title, { color: colors.text }]}>You finished {today.plan_name}! 🎉</Text>
          <Text style={[styles.message, { color: colors.muted }]}>Longest streak: {streak.longest} days</Text>
        </View>
      ) : doneToday ? (
        <>
          <View style={[styles.card, { backgroundColor: colors.card }]}>
            <Text style={[styles.title, { color: colors.text }]}>Done for today 🙏</Text>
            <Text style={[styles.message, { color: colors.muted }]}>
              Tomorrow: {today.reference} (day {today.day_number} of {today.total_days})
            </Text>
          </View>
          <ReadAgain />
        </>
      ) : (
        <>
          <Text style={[styles.day, { color: colors.faint }]}>
            {today.plan_name} · Day {today.day_number} of {today.total_days}
          </Text>
          <Text style={[styles.title, { color: colors.text }]}>{today.reference}</Text>

          <Text style={[passage, { color: colors.text }]}>
            {today.verses.map((v) => (
              <Text key={`${v.chapter}:${v.verse}`}>
                <Text style={[styles.verseNumber, { color: colors.faint }]}>{v.verse} </Text>
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
          <Text style={[styles.message, { color: colors.muted }]}>⏰ Reminder every morning at {wakeTime}</Text>
        ) : (
          <>
            <Text style={[styles.message, { color: colors.muted }]}>Morning reminders are off</Text>
            <Button title="Turn on reminders" onPress={turnOnReminders} />
          </>
        )}
        <Text style={[styles.note, { color: colors.faint }]}>A notification with sound, not an alarm clock.</Text>
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
  // Colours come from the theme (useAppearance), so only sizes and layout live here
  streak: { fontSize: 18, fontWeight: '600', textAlign: 'center' },
  link: { fontSize: 15, textAlign: 'center' },
  card: { borderRadius: 12, padding: 24, gap: 10, alignItems: 'center' },
  day: { fontSize: 14, textTransform: 'uppercase', letterSpacing: 1 },
  title: { fontSize: 26, fontWeight: '700', textAlign: 'center' },
  verseNumber: { fontSize: 13, fontWeight: '700' },
  message: { fontSize: 16, textAlign: 'center' },
  error: { fontSize: 16, textAlign: 'center' },
  reminder: { alignItems: 'center', gap: 8, paddingTop: 8 },
  note: { fontSize: 13, textAlign: 'center' },
});
