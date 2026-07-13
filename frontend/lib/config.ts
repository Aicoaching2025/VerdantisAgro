// One tenant today; every call site reads the slug from here rather than
// hardcoding it, so the seam for multi-tenant is a config change later, not
// a code change (mirrors the backend's tenant-scoped config rule).
export const TENANT_SLUG = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "verdantis";
