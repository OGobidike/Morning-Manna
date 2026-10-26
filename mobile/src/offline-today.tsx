

// The Today screen when there's no connection: the passage comes from the copy saved on
// this phone, and Mark as read is kept here until it can be sent.

import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Passage } from '@/api/client';
import { useAppearance } from '@/appearance';
import { nextOfflinePassage, readToday, type PendingReading, type Snapshot } from '@/offline';

type Props = {
  snapshot: Snapshot;
  pending: PendingReading[];
  onMarkRead: (passage: Passage) => void;
  onRetry: () => void;
};

export function OfflineToday({ snapshot, pending, onMarkRead, onRetry }: Props) {
  const { colors, passage: passageStyle } = useAppearance();

  const next = nextOfflinePassage(snapshot, pending);
  const doneToday = readToday(snapshot, pending);
  const { plan_name, total_days } = snapshot.upcoming;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <View style={[styles.banner, { backgroundColor: colors.card }]}>
        <Text style={[styles.bannerText, { color: colors.text }]}>
          📴 Offline: reading the copy saved on this phone
        </Text>
        <Button title="Try again" onPress={onRetry} />
      </View>

      {snapshot.streak.current > 0 && (
        <Text style={[styles.streak, { color: colors.text }]}>
          🔥 {snapshot.streak.current}-day streak (at your last sync)
        </Text>
      )}

      {doneToday ? (
        <View style={[styles.card, { backgroundColor: colors.card }]}>
          <Text style={[styles.title, { color: colors.text }]}>Done for today 🙏</Text>
          {next && (
            <Text style={[styles.message, { color: colors.muted }]}>
              Tomorrow: {next.reference} (day {next.day_number} of {total_days})
            </Text>
          )}
        </View>
      ) : next ? (
        <>
          <Text style={[styles.day, { color: colors.faint }]}>
            {plan_name} · Day {next.day_number} of {total_days}
          </Text>
          <Text style={[styles.title, { color: colors.text }]}>{next.reference}</Text>
          <Text style={[passageStyle, { color: colors.text }]}>
            {next.verses.map((v) => (
              <Text key={`${v.chapter}:${v.verse}`}>
                <Text style={[styles.verseNumber, { color: colors.faint }]}>{v.verse} </Text>
                {v.text}{' '}
              </Text>
            ))}
          </Text>
          <Button title="Mark as read" onPress={() => onMarkRead(next)} />
        </>
      ) : (
        <View style={[styles.card, { backgroundColor: colors.card }]}>
          <Text style={[styles.message, { color: colors.muted }]}>
            You've read every passage saved on this phone. Connect to get the next ones.
          </Text>
        </View>
      )}

      {pending.length > 0 && (
        <Text style={[styles.note, { color: colors.faint }]}>
          {pending.length} {pending.length === 1 ? 'reading' : 'readings'} waiting to sync
        </Text>
      )}
    </ScrollView>
  );
}

// Colours come from the theme (useAppearance), so only sizes and layout live here
const styles = StyleSheet.create({
  page: { padding: 24, gap: 20 },
  banner: { borderRadius: 12, padding: 16, gap: 8, alignItems: 'center' },
  bannerText: { fontSize: 15, textAlign: 'center' },
  streak: { fontSize: 18, fontWeight: '600', textAlign: 'center' },
  card: { borderRadius: 12, padding: 24, gap: 10, alignItems: 'center' },
  day: { fontSize: 14, textTransform: 'uppercase', letterSpacing: 1 },
  title: { fontSize: 26, fontWeight: '700', textAlign: 'center' },
  verseNumber: { fontSize: 13, fontWeight: '700' },
  message: { fontSize: 16, textAlign: 'center' },
  note: { fontSize: 13, textAlign: 'center' },
});
