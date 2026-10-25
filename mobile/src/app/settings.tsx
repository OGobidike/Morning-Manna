

import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Button,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { getMe, getTranslations, type Me, type Translation, updateMe } from '@/api/client';
import { remindersAllowed, scheduleDailyReminder } from '@/reminders';
import { useSession } from '@/session';
import { dateAt, toHHMM } from '@/time';

// The reader's settings that live on the server: wake time and translation
export default function Settings() {
  const { token } = useSession();

  const [me, setMe] = useState<Me | null>(null);
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([getMe(token), getTranslations()])
      .then(([loadedMe, loadedTranslations]) => {
        setMe(loadedMe);
        setTranslations(loadedTranslations);
      })
      .catch((e) => setMessage(`Couldn't load your settings: ${String(e)}`));
  }, [token]);

  // Save one change, then show what the server now has
  async function save(changes: { wake_time?: string; translation?: string }) {
    if (!token) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateMe(token, changes);
      setMe(updated);

      // A new wake time moves tomorrow's reminder too
      if (changes.wake_time && (await remindersAllowed())) {
        await scheduleDailyReminder(updated.wake_time);
      }
      setMessage('Saved');
    } catch (e) {
      setMessage(`Couldn't save: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  function changeWakeTime() {
    if (!me) return;
    DateTimePickerAndroid.open({
      value: dateAt(me.wake_time),
      mode: 'time',
      onValueChange: (_event, chosen) => save({ wake_time: toHHMM(chosen) }),
    });
  }

  if (!me) {
    return message ? (
      <Text style={[styles.message, styles.page]}>{message}</Text>
    ) : (
      <ActivityIndicator style={styles.loading} size="large" />
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.heading}>Wake time</Text>
      <View style={styles.row}>
        <Text style={styles.value}>{me.wake_time.slice(0, 5)}</Text>
        {Platform.OS === 'android' ? (
          <Button title="Change" onPress={changeWakeTime} disabled={saving} />
        ) : (
          <DateTimePicker
            value={dateAt(me.wake_time)}
            mode="time"
            onValueChange={(_event, chosen) => save({ wake_time: toHHMM(chosen) })}
          />
        )}
      </View>
      <Text style={styles.hint}>Your morning reminder follows this time.</Text>

      <Text style={styles.heading}>Translation</Text>
      {translations.map((t) => (
        <Pressable
          key={t.code}
          onPress={() => t.code !== me.translation && save({ translation: t.code })}
          disabled={saving}
          style={[styles.option, t.code === me.translation && styles.optionChosen]}
        >
          <Text style={styles.optionText}>
            {t.code === me.translation ? '✓ ' : ''}
            {t.name}
          </Text>
        </Pressable>
      ))}

      {saving && <ActivityIndicator />}
      {message && <Text style={styles.message}>{message}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1 },
  page: { padding: 24, gap: 12 },
  heading: { fontSize: 14, color: '#777', textTransform: 'uppercase', letterSpacing: 1, marginTop: 12 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  value: { fontSize: 32, fontWeight: '700' },
  hint: { fontSize: 13, color: '#888' },
  option: { borderWidth: 2, borderColor: '#ddd', borderRadius: 12, padding: 16 },
  optionChosen: { borderColor: '#208AEF', backgroundColor: '#EAF4FE' },
  optionText: { fontSize: 17 },
  message: { fontSize: 15, color: '#555', textAlign: 'center' },
});
