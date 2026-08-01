import "./globals.css";

export const metadata = {
  title: "Финансовый учёт",
  description: "Управленческий учёт для малого бизнеса",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
