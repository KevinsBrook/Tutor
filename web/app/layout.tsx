import type { Metadata } from "next";
import { Noto_Sans_SC, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { GlobalProvider } from "@/context/GlobalContext";
import { AuthProvider } from "@/context/AuthContext";
import ThemeScript from "@/components/ThemeScript";
import AppShell from "@/components/AppShell";
import { I18nClientBridge } from "@/i18n/I18nClientBridge";

const headingFont = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-heading",
});

const bodyFont = Noto_Sans_SC({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "明课学习平台",
  description: "明课学习平台",
  icons: {
    icon: "/mingke-icon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body className={`${headingFont.variable} ${bodyFont.variable}`}>
        <AuthProvider>
          <GlobalProvider>
            <I18nClientBridge>
              <AppShell>{children}</AppShell>
            </I18nClientBridge>
          </GlobalProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
