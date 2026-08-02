import type { Metadata, Viewport } from "next";
import { FavoritesProvider } from "@/components/FavoritesProvider";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "MLB Edge",
  description: "Daily MLB board, props, and moneyline tickets."
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
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
