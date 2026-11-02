

// The daily morning reminder: a notification the phone schedules for itself at the wake time.
// It isn't an alarm clock: Android and iOS don't let ordinary apps ring like one.

import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import type { ReminderVariant } from '@/api/client';

const CHANNEL_ID = 'morning-reminder';

// The reminder experiment's two wordings. A is the one readers have always had; B is being
// tested against it. Each reader's group comes from the server, so it's the same on every phone.
export const REMINDER_WORDING: Record<ReminderVariant, { title: string; body: string }> = {
  A: { title: 'Good morning ☀️', body: 'Your passage for today is ready.' },
  B: {
    title: 'New every morning ☀️',
    body: "Today's passage is waiting for you. (Lam 3:22–23)",
  },
};

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

// One reminder every day at the wake time ("06:30" or "06:30:00"), in the reader's own
// wording, replacing any earlier one
export async function scheduleDailyReminder(
  wakeTime: string,
  variant: ReminderVariant,
): Promise<void> {
  const [hour, minute] = wakeTime.split(':').map(Number);
  await ensureChannel();
  await Notifications.cancelAllScheduledNotificationsAsync();
  await Notifications.scheduleNotificationAsync({
    content: REMINDER_WORDING[variant],
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour,
      minute,
      channelId: CHANNEL_ID,
    },
  });
}

// For testing: a one-off reminder a few seconds from now (it doesn't touch the daily one)
export async function sendTestReminder(variant: ReminderVariant, seconds = 10): Promise<void> {
  await ensureChannel();
  await Notifications.scheduleNotificationAsync({
    content: { title: REMINDER_WORDING[variant].title, body: 'This is how your reminder will look.' },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds,
      channelId: CHANNEL_ID,
    },
  });
}


// Call back once for every reminder the reader taps, including a tap that opened the app.
// Returns a function that stops listening.
let lastTap: string | null = null;

export function onReminderTapped(callback: () => void): () => void {
  function handle(response: Notifications.NotificationResponse | null) {
    if (!response) return;
    // The same tap can arrive twice (at launch and through the listener): count it once
    const tap = `${response.notification.request.identifier}:${response.notification.date}`;
    if (tap === lastTap) return;
    lastTap = tap;
    Notifications.clearLastNotificationResponse();
    callback();
  }

  // A tap that launched the app happened before this listener existed
  handle(Notifications.getLastNotificationResponse());
  const subscription = Notifications.addNotificationResponseReceivedListener(handle);
  return () => subscription.remove();
}
