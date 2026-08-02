import { Link, Stack } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { colors } from "@/lib/theme";

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: "Not found" }} />
      <View style={styles.container}>
        <Text style={styles.title}>Screen not found</Text>
        <Link href="/" style={styles.link}>
          <Text style={styles.linkText}>Back to Board</Text>
        </Link>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  title: {
    color: colors.text,
    fontFamily: "DMSans_700Bold",
    fontSize: 18,
  },
  link: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: colors.text,
    borderRadius: 8,
  },
  linkText: {
    color: colors.bg,
    fontFamily: "DMSans_700Bold",
  },
});
