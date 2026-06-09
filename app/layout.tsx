import type { Metadata } from "next";
import { FavoritesProvider } from "@/components/FavoritesProvider";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "MLB Edge",
  description: "Daily MLB predictions, best bets, team stats, model accuracy, and watch links."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <FavoritesProvider>
          <Nav />
          {children}
        </FavoritesProvider>
      </body>
    </html>
  );
}
