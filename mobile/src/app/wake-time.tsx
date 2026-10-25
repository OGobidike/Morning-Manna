

import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { router } from 'expo-router';
import { useState } from 'react';
import { Button, Platform, StyleSheet, Text, View } from 'react-native';

import { toHHMM } from '@/time';


// Onboarding 2 of 3
export default function WakeTime() {
  // Start at 06:00 today; only the hours and minutes matter
  const [time, setTime] = useState(() => {
    const sixAm = new Date();
    sixAm.setHours(6, 0, 0, 0);
    return sixAm;
  });

  // Android shows the picker as a pop-up dialog
  function openPicker() {
    DateTimePickerAndroid.open({
      value: time,
      mode: 'time',
      onValueChange: (_event, chosen) => setTime(chosen),
    });
  }

  return (
    <View style={styles.container}>
      <Text style={styles.question}>When do you usually wake up?</Text>
      <Text style={styles.time}>{toHHMM(time)}</Text>

      {Platform.OS === 'android' ? (
        <Button title="Change time" onPress={openPicker} />
      ) : (
        <DateTimePicker
          value={time}
          mode="time"
          display="spinner"
          onValueChange={(_event, chosen) => setTime(chosen)}
        />
      )}

      <Button
        title="Next"
        onPress={() => router.push({ pathname: '/plan', params: { wakeTime: toHHMM(time) } })}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 24, padding: 32 },
  question: { fontSize: 20, textAlign: 'center' },
  time: { fontSize: 56, fontWeight: '700' },
});
