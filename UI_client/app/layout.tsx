import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '車況管家｜iRent AI Prototype',
  description: '從拍攝防呆、AI 判讀到人工覆核與派工的車況閉環 Prototype。',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
