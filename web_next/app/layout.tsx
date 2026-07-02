import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Route Finder",
  description: "Simple route finder (bus/train/flight)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}

