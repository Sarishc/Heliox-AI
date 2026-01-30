import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { CommandPalette } from "@/components/ui/CommandPalette";

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
          {children}
          <CommandPalette />
        </ToastProvider>
      </body>
    </html>
  );
}
