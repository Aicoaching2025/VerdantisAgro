import { clerkMiddleware } from "@clerk/nextjs/server";

// Path-matching auth checks (createRouteMatcher + auth.protect() here) are
// deprecated as of this Clerk version -- protection now lives as a
// resource-based check in each protected layout/page instead (see
// app/(dashboard)/layout.tsx), since middleware-based path matching can
// diverge from how Next.js actually routes requests. This proxy only
// attaches the auth context so `auth()` works in Server Components.
export default clerkMiddleware();

export const config = {
  matcher: ["/((?!_next|.*\\.\\w+$).*)"],
};
