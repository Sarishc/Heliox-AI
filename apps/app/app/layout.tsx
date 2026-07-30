import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "./brand-surfaces.css";
import "../styles/design-tokens.css";
import { ToastProvider } from "@/components/ui/Toast";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { SuppressRechartsWarnings } from "@/components/SuppressRechartsWarnings";
import { DemoBanner } from "@/components/DemoBanner";
import { DemoProvider } from "@/components/DemoProvider";
import { EventProviders } from "@/components/EventProviders";
import { PageTransition } from "@/components/motion/PageTransition";

const inter = Inter({ 
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  title: {
    default: "Heliox — GPU Infrastructure Intelligence",
    template: "%s · Heliox",
  },
  description: "Control GPU spend, utilization, forecasting, and optimization from one operational system.",
  icons: {
    icon: "/heliox-mark.svg",
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "Heliox — GPU Infrastructure Intelligence",
    description: "Operational clarity for GPU cost and performance.",
    images: [{ url: "/heliox-social.png", width: 512, height: 512, alt: "Heliox" }],
  },
  twitter: {
    card: "summary",
    title: "Heliox — GPU Infrastructure Intelligence",
    description: "Operational clarity for GPU cost and performance.",
    images: ["/heliox-social.png"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body className={inter.className}>
        <ToastProvider>
          <DemoProvider>
            <EventProviders>
              <DemoBanner />
              <SuppressRechartsWarnings />
              <PageTransition>{children}</PageTransition>
              <CommandPalette />
            </EventProviders>
          </DemoProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
