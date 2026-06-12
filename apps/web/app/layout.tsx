import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QAAgent",
  description: "Paper search, PDF reading, and cited question answering"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
