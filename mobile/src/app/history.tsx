

import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { getHistory, type History } from '@/api/client';
import { useAppearance } from '@/appearance';
import { buildWeeks, daysCovered, isoDay, monthLabel, parseDay } from '@/calendar';
import { useSession } from '@/session';

const CELL = 16;
const GAP = 4;
// Width of the weekday names column on the left
const LABEL = 26;
// Monday-first rows; only every other day is labelled, to keep it calm
const WEEKDAYS = ['Mon', '', 'Wed', '', 'Fri', '', ''];

// A heat map of every morning read: one column per week, one square per day
export default function HistoryScreen() {
  const { token } = useSession();
  const { colors } = useAppearance();

  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reload whenever the screen comes into view, so a new reading shows up straight away
  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      getHistory(token)
        .then(setHistory)
        .catch((e) => setError(`Couldn't load your history: ${String(e)}`));
    }, [token]),
  );

  if (error) return <Text style={[styles.message, { color: colors.error }]}>{error}</Text>;
  if (!history) return <ActivityIndicator style={styles.loading} size="large" color={colors.accent} />;

  const read = new Set(history.days);
  const start = parseDay(history.start);
  const end = parseDay(history.end);
  const weeks = buildWeeks(start, end);
  const weeksCovered = Math.round(daysCovered(start, end) / 7);

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={[styles.total, { color: colors.text }]}>
        {history.days.length} {history.days.length === 1 ? 'morning' : 'mornings'}
      </Text>
      <Text style={[styles.message, { color: colors.muted }]}>read in the last {weeksCovered} weeks</Text>

      {/* Month names, one slot per week column, above the grid */}
      <View style={styles.months}>
        {weeks.map((week, w) => (
          <Text key={w} style={[styles.monthLabel, { color: colors.faint }]} numberOfLines={1}>
            {monthLabel(week, w === 0)}
          </Text>
        ))}
      </View>

      <View style={styles.grid}>
        {/* Weekday names down the left */}
        <View style={styles.column}>
          {WEEKDAYS.map((name, i) => (
            <Text key={i} style={[styles.dayLabel, { color: colors.faint }]}>
              {name}
            </Text>
          ))}
        </View>

        {/* One column per week, Monday at the top */}
        {weeks.map((week, w) => (
          <View key={w} style={styles.column}>
            {week.map((day, d) => {
              if (!day) return <View key={d} style={styles.cell} />;
              const iso = isoDay(day);
              const wasRead = read.has(iso);
              return (
                <View
                  key={d}
                  accessibilityLabel={`${iso}: ${wasRead ? 'read' : 'not read'}`}
                  style={[
                    styles.cell,
                    { backgroundColor: wasRead ? colors.accent : colors.border },
                    iso === history.end && { borderWidth: 2, borderColor: colors.text },
                  ]}
                />
              );
            })}
          </View>
        ))}
      </View>

      <View style={styles.legend}>
        <View style={[styles.cell, { backgroundColor: colors.border }]} />
        <Text style={[styles.legendText, { color: colors.muted }]}>not read</Text>
        <View style={[styles.cell, { backgroundColor: colors.accent }]} />
        <Text style={[styles.legendText, { color: colors.muted }]}>read</Text>
        <View style={[styles.cell, { borderWidth: 2, borderColor: colors.text }]} />
        <Text style={[styles.legendText, { color: colors.muted }]}>today</Text>
      </View>
    </ScrollView>
  );
}

// Colours come from the theme (useAppearance), so only sizes and layout live here
const styles = StyleSheet.create({
  loading: { flex: 1 },
  page: { padding: 24, gap: 12 },
  total: { fontSize: 28, fontWeight: '700' },
  message: { fontSize: 16 },
  // Each week column is CELL wide with GAP after it, so labels and squares line up
  months: { flexDirection: 'row', marginTop: 8, paddingLeft: LABEL + GAP },
  monthLabel: { width: CELL + GAP, fontSize: 10, overflow: 'visible' },
  grid: { flexDirection: 'row', gap: GAP },
  column: { gap: GAP },
  cell: { width: CELL, height: CELL, borderRadius: 4 },
  dayLabel: { height: CELL, width: LABEL, fontSize: 10, lineHeight: CELL },
  legend: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 },
  legendText: { fontSize: 13, marginRight: 8 },
});
