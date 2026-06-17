import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "./lib/theme";

export const metadata: Metadata = {
  title: "Safewalk",
  description: "Safe last-mile walking routes for MARTA riders"
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
