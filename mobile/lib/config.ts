/** Production site the iOS app embeds. */
export const SITE_URL =
  process.env.EXPO_PUBLIC_API_BASE ?? "https://mlb-edge-woad.vercel.app";

export const APP_TABS = [
  { name: "index", title: "Board", path: "/", glyph: "◆" },
  { name: "props", title: "Props", path: "/props", glyph: "☰" },
  { name: "moneyline", title: "Moneyline", path: "/best-bets", glyph: "$" },
  { name: "watch", title: "Watch", path: "/watch", glyph: "▶" },
  { name: "accuracy", title: "Accuracy", path: "/accuracy", glyph: "%" },
] as const;
