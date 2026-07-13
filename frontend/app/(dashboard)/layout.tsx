import { auth } from "@clerk/nextjs/server";

import { DashboardNav } from "@/components/dashboard-nav";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Resource-based auth check (not path-matching middleware -- see
  // proxy.ts). Every route under this layout requires a signed-in user;
  // auth.protect() redirects to sign-in otherwise.
  await auth.protect();

  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <DashboardNav />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
