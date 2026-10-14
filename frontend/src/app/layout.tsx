import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import Aurora from "@/components/aurora/Aurora";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Synpo GTM Console",
  description: "Internal dashboard for the Synpo Instagram creator GTM pipeline.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        {/* Ambient background. Fixed, non-interactive, behind all content. */}
        <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
          <Aurora
            colorStops={["#0ea5e9", "#22c98a", "#14b8a6"]}
            amplitude={0.8}
            blend={0.65}
            height={0.4}
            speed={0.55}
            scale={0.9}
            glow={0.5}
            brightness={0.85}
            layers={2}
            direction="top"
            mouseInteraction
            opacity={0.6}
            intro
          />
        </div>
        {children}
      </body>
    </html>
  );
}
