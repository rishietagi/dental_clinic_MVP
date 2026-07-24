import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/app-shell";
import { Toaster } from "@/components/ui/sonner";

// Set the theme BEFORE first paint so a dark user never flashes light. Reads the
// saved choice, else the OS preference; stamps data-theme (wins over the media
// query) and the .dark class (drives Tailwind `dark:` variants).
const themeScript = `
(function(){try{
  var s=localStorage.getItem('theme');
  var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;
  var r=document.documentElement;
  r.dataset.theme=d?'dark':'light';
  r.classList.toggle('dark',d);
}catch(e){}})();
`;

// Must be --font-sans: globals.css maps Tailwind's font-sans to var(--font-sans).
// shadcn's init renamed it, so the scaffold's --font-geist-sans no longer matches
// and text silently falls back to serif.
const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Dental Clinic",
  description: "Clinic management system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col">
        <AppShell>{children}</AppShell>
        <Toaster />
      </body>
    </html>
  );
}
