import type { Metadata } from "next";
import { ToastProvider } from "../components/ui/toast";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MediGest | Atención médica",
    template: "%s | MediGest",
  },
  description: "Plataforma de gestión de atención médica",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
