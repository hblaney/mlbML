import { Tabs } from "expo-router";
import { Text } from "react-native";

import { APP_TABS } from "@/lib/config";
import { colors } from "@/lib/theme";

function TabGlyph({ label, color }: { label: string; color: string }) {
  return (
    <Text style={{ color, fontSize: 15, fontFamily: "DMSans_700Bold" }}>{label}</Text>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.bg,
          borderTopColor: colors.border,
        },
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: "DMSans_500Medium", fontSize: 10 },
      }}
    >
      {APP_TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ color }) => <TabGlyph label={tab.glyph} color={String(color)} />,
          }}
        />
      ))}
    </Tabs>
  );
}
