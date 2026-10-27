

// On the "Done for today" screen: open today's passage again, from the copy saved at Mark as read

import { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';

import { useAppearance } from '@/appearance';
import { isoDay } from '@/calendar';
import { type LastRead, loadLastRead } from '@/offline';

export function ReadAgain() {
  const { colors, passage: passageStyle } = useAppearance();
  const [lastRead, setLastRead] = useState<LastRead | null>(null);
  const [open, setOpen] = useState(false);

  // Read the saved copy once, when the button first appears
  useEffect(() => {
    void loadLastRead().then(setLastRead);
  }, []);

  // Only today's passage: one read yesterday isn't the one this screen is about
  if (!lastRead || lastRead.read_on !== isoDay(new Date())) return null;

  if (!open) return <Button title="Read today's passage again" onPress={() => setOpen(true)} />;

  return (
    <View style={styles.box}>
      <Text style={[styles.reference, { color: colors.text }]}>{lastRead.reference}</Text>
      <Text style={[passageStyle, { color: colors.text }]}>
        {lastRead.verses.map((v) => (
          <Text key={`${v.chapter}:${v.verse}`}>
            <Text style={[styles.verseNumber, { color: colors.faint }]}>{v.verse} </Text>
            {v.text}{' '}
          </Text>
        ))}
      </Text>
      <Button title="Close" onPress={() => setOpen(false)} />
    </View>
  );
}

// Colours come from the theme (useAppearance), so only sizes and layout live here
const styles = StyleSheet.create({
  box: { gap: 12 },
  reference: { fontSize: 22, fontWeight: '700', textAlign: 'center' },
  verseNumber: { fontSize: 13, fontWeight: '700' },
});
