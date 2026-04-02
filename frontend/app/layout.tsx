import type { Metadata } from "next";
import "./globals.css";
import Navbar from "./components/Navbar";

export const metadata: Metadata = {
  title: "SimpleSeed — RFP Intelligence",
  description: "AI-powered RFP analysis, scoring, and proposal generation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-[#1e2d22] py-4 text-center text-xs text-[#6b8f72]">
          SimpleSeed v1.0 — RFP Intelligence Platform
        </footer>
      </body>
    </html>
  );
}
