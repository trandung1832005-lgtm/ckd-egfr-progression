import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Theo dõi chức năng thận (eGFR)",
  description: "Theo dõi eGFR theo thời gian, dự đoán xu hướng và hướng dẫn chăm sóc bệnh thận mạn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
