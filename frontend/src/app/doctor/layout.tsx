import RoleShell from "@/components/Shell";

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
  return <RoleShell role="doctor">{children}</RoleShell>;
}
