

// How the app looks on this phone: light or dark, and how big the passage text is.
// Saved on the device (not the server): it's about this screen, not the reader.

import * as SecureStore from 'expo-secure-store';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

export type ThemeName = 'light' | 'dark';
export type TextSize = 'small' | 'medium' | 'large';

// Every colour the screens use, by purpose
export type Colors = {
  background: string;
  card: string;
  text: string;
  muted: string;
  faint: string;
  border: string;
  accent: string;
  accentSoft: string;
  error: string;
};

export const palettes: Record<ThemeName, Colors> = {
  light: {
    background: '#FFFFFF',
    card: '#F4F1EA',
    text: '#1A1A1A',
    muted: '#555555',
    faint: '#888888',
    border: '#DDDDDD',
    accent: '#208AEF',
    accentSoft: '#EAF4FE',
    error: '#B3261E',
  },
  dark: {
    background: '#121212',
    card: '#24211C',
    text: '#ECECEC',
    muted: '#B5B5B5',
    faint: '#8A8A8A',
    border: '#3A3A3A',
    accent: '#5AAEF7',
    accentSoft: '#15293B',
    error: '#F2B8B5',
  },
};

// Passage text at each size: font size and the space between lines
export const passageSizes: Record<TextSize, { fontSize: number; lineHeight: number }> = {
  small: { fontSize: 18, lineHeight: 28 },
  medium: { fontSize: 21, lineHeight: 34 },
  large: { fontSize: 25, lineHeight: 40 },
};

// Saved with SecureStore because it's already in the app: no new native module, no rebuild
const THEME_KEY = 'morning-manna.theme';
const SIZE_KEY = 'morning-manna.text-size';

type Appearance = {
  theme: ThemeName;
  textSize: TextSize;
  colors: Colors;
  passage: { fontSize: number; lineHeight: number };
  setTheme: (theme: ThemeName) => void;
  setTextSize: (size: TextSize) => void;
};

const AppearanceContext = createContext<Appearance | null>(null);

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>('light');
  const [textSize, setTextSizeState] = useState<TextSize>('medium');

  // Read the saved choices once, when the app starts
  useEffect(() => {
    (async () => {
      const savedTheme = await SecureStore.getItemAsync(THEME_KEY);
      const savedSize = await SecureStore.getItemAsync(SIZE_KEY);
      if (savedTheme === 'light' || savedTheme === 'dark') setThemeState(savedTheme);
      if (savedSize === 'small' || savedSize === 'medium' || savedSize === 'large') {
        setTextSizeState(savedSize);
      }
    })();
  }, []);

  function setTheme(next: ThemeName) {
    setThemeState(next);
    SecureStore.setItemAsync(THEME_KEY, next);
  }

  function setTextSize(next: TextSize) {
    setTextSizeState(next);
    SecureStore.setItemAsync(SIZE_KEY, next);
  }

  return (
    <AppearanceContext.Provider
      value={{
        theme,
        textSize,
        colors: palettes[theme],
        passage: passageSizes[textSize],
        setTheme,
        setTextSize,
      }}
    >
      {children}
    </AppearanceContext.Provider>
  );
}

// Use the appearance in any screen
export function useAppearance(): Appearance {
  const appearance = useContext(AppearanceContext);
  if (!appearance) throw new Error('useAppearance must be used inside <AppearanceProvider>');
  return appearance;
}
