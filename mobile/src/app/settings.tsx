

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
import { type TextSize, type ThemeName, useAppearance } from '@/appearance';
import { remindersAllowed, scheduleDailyReminder } from '@/reminders';
import { useSession } from '@/session';
import { dateAt, toHHMM } from '@/time';

const THEMES: { value: ThemeName; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

const SIZES: { value: TextSize; label: string }[] = [
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
  { value: 'large', label: 'Large' },
];

type OptionProps = { label: string; chosen: boolean; disabled?: boolean; onPress: () => void };

// One tappable choice; the chosen one gets the accent border and a ✓
function Option({ label, chosen, disabled, onPress }: OptionProps) {
  const { colors } = useAppearance();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.option,
        { borderColor: colors.border },
        chosen && { borderColor: colors.accent, backgroundColor: colors.accentSoft },
      ]}
    >
      <Text style={[styles.optionText, { color: colors.text }]}>
        {chosen ? '✓ ' : ''}
        {label}
      </Text>
    </Pressable>
  );
}

// Settings saved on the server (wake time, translation) and on this phone (appearance)
export default function Settings() {
  const { token } = useSession();
  const { colors, passage, theme, setTheme, textSize, setTextSize } = useAppearance();

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
      <Text style={[styles.message, styles.page, { color: colors.muted }]}>{message}</Text>
    ) : (
      <ActivityIndicator style={styles.loading} size="large" color={colors.accent} />
    );
  }

  const heading = [styles.heading, { color: colors.faint }];

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={heading}>Wake time</Text>
      <View style={styles.row}>
        <Text style={[styles.value, { color: colors.text }]}>{me.wake_time.slice(0, 5)}</Text>
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
      <Text style={[styles.hint, { color: colors.faint }]}>Your morning reminder follows this time.</Text>

      <Text style={heading}>Translation</Text>
      {translations.map((t) => (
        <Option
          key={t.code}
          label={t.name}
          chosen={t.code === me.translation}
          disabled={saving}
          onPress={() => t.code !== me.translation && save({ translation: t.code })}
        />
      ))}

      <Text style={heading}>Appearance</Text>
      <View style={styles.choices}>
        {THEMES.map((t) => (
          <Option key={t.value} label={t.label} chosen={t.value === theme} onPress={() => setTheme(t.value)} />
        ))}
      </View>

      <Text style={heading}>Text size</Text>
      <View style={styles.choices}>
        {SIZES.map((s) => (
          <Option key={s.value} label={s.label} chosen={s.value === textSize} onPress={() => setTextSize(s.value)} />
        ))}
      </View>
      <Text style={[passage, { color: colors.text }]}>Blessed is the man that walketh not…</Text>

      {saving && <ActivityIndicator color={colors.accent} />}
      {message && <Text style={[styles.message, { color: colors.muted }]}>{message}</Text>}
    </ScrollView>
  );
}

// Colours come from the theme (useAppearance), so only sizes and layout live here
const styles = StyleSheet.create({
  loading: { flex: 1 },
  page: { padding: 24, gap: 12 },
  heading: { fontSize: 14, textTransform: 'uppercase', letterSpacing: 1, marginTop: 12 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  value: { fontSize: 32, fontWeight: '700' },
  hint: { fontSize: 13 },
  choices: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  option: { borderWidth: 2, borderRadius: 12, padding: 16 },
  optionText: { fontSize: 17 },
  message: { fontSize: 15, textAlign: 'center' },
});
