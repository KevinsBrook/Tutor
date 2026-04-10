import type { Metadata } from "next";
import { Noto_Sans_SC, Space_Grotesk } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import { GlobalProvider } from "@/context/GlobalContext";
import ThemeScript from "@/components/ThemeScript";
import LayoutWrapper from "@/components/LayoutWrapper";
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
  title: "DeepTutor Platform",
  description: "Multi-Agent Teaching & Research Copilot",
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
        <GlobalProvider>
          <I18nClientBridge>
            <LayoutWrapper>
              <div className="ui-shell min-h-screen overflow-hidden transition-colors duration-200">
                <Sidebar />
                <main className="mx-auto w-full max-w-[1800px] flex-1 px-3 pb-4 pt-3 md:px-6 md:pb-6 md:pt-4">
                  {children}
                </main>
              </div>
            </LayoutWrapper>
          </I18nClientBridge>
        </GlobalProvider>
      </body>
    </html>
  );
}
