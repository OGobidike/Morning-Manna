

// The daily morning reminder: a notification the phone schedules for itself at the wake time.
// It isn't an alarm clock: Android and iOS don't let ordinary apps ring like one.

import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

const CHANNEL_ID = 'morning-reminder';

// Show the reminder even if the app happens to be open when it fires
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

// Android groups notifications into channels, which readers can mute in system settings.
// On Android 13+, the permission prompt only appears once a channel exists.
async function ensureChannel(): Promise<void> {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: 'Morning reminder',
      importance: Notifications.AndroidImportance.HIGH,
    });
  }
}

// Ask for permission. Android only lets an app ask a limited number of times.
export async function askForReminders(): Promise<boolean> {
  await ensureChannel();
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) return false;
  return (await Notifications.requestPermissionsAsync()).granted;
}

// Is the reader currently allowing notifications? (Never shows a prompt.)
export async function remindersAllowed(): Promise<boolean> {
  return (await Notifications.getPermissionsAsync()).granted;
}

// One reminder every day at the wake time ("06:30" or "06:30:00"), replacing any earlier one
export async function scheduleDailyReminder(wakeTime: string): Promise<void> {
  const [hour, minute] = wakeTime.split(':').map(Number);
  await ensureChannel();
  await Notifications.cancelAllScheduledNotificationsAsync();
  await Notifications.scheduleNotificationAsync({
    content: { title: 'Good morning ☀️', body: 'Your passage for today is ready.' },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour,
      minute,
      channelId: CHANNEL_ID,
    },
  });
}

// For testing: a one-off reminder a few seconds from now (it doesn't touch the daily one)
export async function sendTestReminder(seconds = 10): Promise<void> {
  await ensureChannel();
  await Notifications.scheduleNotificationAsync({
    content: { title: 'Good morning ☀️', body: 'This is how your reminder will look.' },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds,
      channelId: CHANNEL_ID,
    },
  });
}
