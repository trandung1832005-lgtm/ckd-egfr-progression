import RoleShell from "@/components/Shell";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return <RoleShell role="patient">{children}</RoleShell>;
}
