import {
  BebasNeue_400Regular,
  useFonts as useBebas,
} from "@expo-google-fonts/bebas-neue";
import {
  DMSans_500Medium,
  DMSans_700Bold,
  useFonts as useDmSans,
} from "@expo-google-fonts/dm-sans";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import "react-native-reanimated";

import { colors } from "@/lib/theme";

export { ErrorBoundary } from "expo-router";

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [bebasLoaded] = useBebas({ BebasNeue_400Regular });
  const [dmLoaded] = useDmSans({ DMSans_500Medium, DMSans_700Bold });
  const loaded = bebasLoaded && dmLoaded;

  useEffect(() => {
    if (loaded) void SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          contentStyle: { backgroundColor: colors.bg },
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.text,
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      </Stack>
    </>
  );
}
