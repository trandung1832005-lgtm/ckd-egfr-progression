import RoleShell from "@/components/Shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RoleShell role="admin">{children}</RoleShell>;
}
