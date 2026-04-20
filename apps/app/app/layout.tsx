import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { SuppressRechartsWarnings } from "@/components/SuppressRechartsWarnings";
import { DemoBanner } from "@/components/DemoBanner";
import { DemoProvider } from "@/components/DemoProvider";
import { EventProviders } from "@/components/EventProviders";

const inter = Inter({ 
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Heliox Dashboard - GPU Cost Analytics",
  description: "Real-time GPU cost analytics and insights for ML workloads",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ToastProvider>
          <DemoProvider>
            <EventProviders>
              <DemoBanner />
              <SuppressRechartsWarnings />
              {children}
              <CommandPalette />
            </EventProviders>
          </DemoProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
