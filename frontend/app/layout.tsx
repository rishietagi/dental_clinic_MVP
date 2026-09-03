import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/app-shell";
import { Toaster } from "@/components/ui/sonner";

// LIGHT ONLY (10.6). Stamped before first paint, as it always was, but the
// choice is now fixed rather than read from localStorage or the OS.
//
// Why: the app runs on one shared PC at the clinic's front desk. It followed
// Windows' theme, so if that machine were set to dark mode the app would open
// dark — and the sun/moon toggle that used to sit in the sidebar was one more
// thing to press by accident on a screen used all day. One look, always.
//
// The dark palette is still in globals.css and the `dark:` variants still work,
// so restoring the choice means putting the old script and the toggle back.
const themeScript = `
(function(){try{
  var r=document.documentElement;
  r.dataset.theme='light';
  r.classList.remove('dark');
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
