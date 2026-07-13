import Link from "next/link";
import { UserButton } from "@clerk/nextjs";

import { cn } from "@/lib/utils";

const SECTIONS = [
  { href: "/inbox", label: "Lead Inbox" },
  { href: "/approvals", label: "Approvals" },
  { href: "/intake", label: "Intake" },
  { href: "/admin", label: "Admin" },
];

export function DashboardNav() {
  return (
    <nav
      className={cn(
        "flex shrink-0 items-center gap-1 border-b p-3 md:w-56 md:flex-col md:items-stretch md:border-r md:border-b-0 md:p-4",
      )}
    >
      <Link href="/" className="mb-4 hidden text-sm font-semibold md:block">
        Verdantis
      </Link>
      <div className="flex flex-1 flex-wrap gap-1 md:flex-col">
        {SECTIONS.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {section.label}
          </Link>
        ))}
      </div>
      <div className="ml-auto md:mt-4 md:ml-0">
        <UserButton />
      </div>
    </nav>
  );
}
