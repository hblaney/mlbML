import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { WebView } from "react-native-webview";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { SITE_URL } from "@/lib/config";
import { colors } from "@/lib/theme";

type Props = {
  path: string;
};

/** Hide the website chrome — the app has its own tab bar. */
const INJECTED = `
(function () {
  var css = document.createElement('style');
  css.textContent = [
    '.site-header { display: none !important; }',
    'body { padding-top: 0 !important; }',
    'html { background: #030406 !important; }',
  ].join('\\n');
  (document.head || document.documentElement).appendChild(css);
  true;
})();
`;

export function AppWebView({ path }: Props) {
  const insets = useSafeAreaInsets();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const uri = `${SITE_URL}${path}${path.includes("?") ? "&" : "?"}native=1`;

  const reload = useCallback(() => {
    setError(null);
    setLoading(true);
    webRef.current?.reload();
  }, []);

  if (error) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.errorTitle}>Couldn’t load MLB Edge</Text>
        <Text style={styles.errorBody}>{error}</Text>
        <Pressable onPress={reload} style={styles.retry}>
          <Text style={styles.retryText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      {loading ? (
        <View style={styles.loading} pointerEvents="none">
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : null}

      <WebView
        ref={webRef}
        source={{ uri }}
        style={styles.flex}
        onLoadStart={() => {
          setLoading(true);
          setError(null);
        }}
        onLoadEnd={() => setLoading(false)}
        onError={(e) => {
          setLoading(false);
          setError(e.nativeEvent.description || "Network error");
        }}
        onHttpError={(e) => {
          if (e.nativeEvent.statusCode >= 400) {
            setError(`HTTP ${e.nativeEvent.statusCode}`);
          }
        }}
        injectedJavaScript={INJECTED}
        injectedJavaScriptBeforeContentLoaded={INJECTED}
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        allowsFullscreenVideo
        javaScriptEnabled
        domStorageEnabled
        sharedCookiesEnabled
        setSupportMultipleWindows={false}
        applicationNameForUserAgent="MLBEdgeApp/1.0"
        pullToRefreshEnabled
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1, backgroundColor: colors.bg },
  loading: {
    ...StyleSheet.absoluteFill,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
    backgroundColor: colors.bg,
  },
  center: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 10,
  },
  errorTitle: {
    color: colors.text,
    fontFamily: "DMSans_700Bold",
    fontSize: 18,
  },
  errorBody: {
    color: colors.muted,
    fontFamily: "DMSans_500Medium",
    textAlign: "center",
  },
  retry: {
    marginTop: 8,
    backgroundColor: colors.text,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: {
    color: colors.bg,
    fontFamily: "DMSans_700Bold",
  },
});
