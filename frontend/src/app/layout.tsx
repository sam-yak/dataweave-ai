import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataWeave AI — Messy CSV in. Clean data out.",
  description:
    "Upload your messy spreadsheet. Our 5 AI agents map columns, normalize formats, and validate every row — in under 60 seconds.",
  openGraph: {
    title: "DataWeave AI — Messy CSV in. Clean data out.",
    description:
      "Upload your messy spreadsheet. Our 5 AI agents map columns, normalize formats, and validate every row — in under 60 seconds.",
    url: "https://dataweaveai.co",
    siteName: "DataWeave AI",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "DataWeave AI — Messy CSV in. Clean data out.",
    description:
      "5 AI agents turn messy CSVs into clean, schema-compliant data in under 60 seconds.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
