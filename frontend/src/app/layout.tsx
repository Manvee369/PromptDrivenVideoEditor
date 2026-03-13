import React from 'react';
import type { Metadata } from 'next';
import '@/styles/globals.css';
import { Sidebar } from './Sidebar';

export const metadata: Metadata = {
  title: 'Prompt Editor',
  description: 'AI-powered prompt-driven video editor',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50
                     focus:px-4 focus:py-2 focus:rounded-[var(--radius-md)]
                     focus:bg-[var(--accent)] focus:text-white focus:text-sm focus:font-medium"
        >
          Skip to main content
        </a>
        <div className="flex h-screen overflow-hidden bg-[var(--background)]">
          {/* Fixed sidebar */}
          <Sidebar />

          {/* Scrollable main content */}
          <main
            className="flex-1 overflow-y-auto"
            id="main-content"
            role="main"
          >
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
