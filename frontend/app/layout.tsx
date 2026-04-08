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
      <body className="min-h-screen flex flex-col bg-[#09090b]">
        <Navbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-[#27272a] py-5 text-center text-xs text-[#52525b]">
          SimpleSeed &copy; {new Date().getFullYear()} &mdash; RFP Intelligence Platform
        </footer>
      </body>
    </html>
  );
}
