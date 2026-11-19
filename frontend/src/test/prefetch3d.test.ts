import { canPrefetch } from "@/lib/prefetch3d";

describe("canPrefetch", () => {
  it("prefetches when the connection is unknown (iOS) or 4G", () => {
    expect(canPrefetch(undefined)).toBe(true);
    expect(canPrefetch({})).toBe(true);
    expect(canPrefetch({ effectiveType: "4g" })).toBe(true);
  });

  it("never on Data Saver or a slow connection", () => {
    expect(canPrefetch({ saveData: true, effectiveType: "4g" })).toBe(false);
    for (const effectiveType of ["slow-2g", "2g", "3g"]) expect(canPrefetch({ effectiveType })).toBe(false);
  });
});
