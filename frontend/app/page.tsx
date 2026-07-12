import Link from "next/link";
import { Button } from "@/components/ui/button";

const SECTIONS = [
  { href: "/inbox", label: "Lead Inbox" },
  { href: "/approvals", label: "Approval / Outreach" },
  { href: "/intake", label: "Inbound Intake" },
  { href: "/admin", label: "Admin / Settings" },
];

export default function Home() {
  return (
    <main className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-semibold">Verdantis Buy-Side Lead-Gen</h1>
      <p className="text-muted-foreground max-w-md text-center">
        Buyer discovery, verification, and inbound qualification for
        Verdantis Agro Produce.
      </p>
      <nav className="flex flex-wrap justify-center gap-3">
        {SECTIONS.map((section) => (
          <Button key={section.href} variant="outline" asChild>
            <Link href={section.href}>{section.label}</Link>
          </Button>
        ))}
      </nav>
    </main>
  );
}
