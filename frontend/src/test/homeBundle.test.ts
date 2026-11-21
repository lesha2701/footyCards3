import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { HOME_PARTS, seedHome } from "@/lib/homeBundle";

describe("homeBundle", () => {
  it("puts each part under its query's own key and skips the failed ones", () => {
    const client = new QueryClient();
    const seeded = seedHome(client, {
      data: { "/profile/me": { id: 1 }, "/presence": null, "/packs": [{ id: 7 }] },
      errors: { "/clubs/me": 404 },
    });
    expect(seeded).toBe(3);
    expect(client.getQueryData(["profile", "me"])).toEqual({ id: 1 });
    expect(client.getQueryData(["packs"])).toEqual([{ id: 7 }]);
    // null is an answer too («no presence check»), not a missing part.
    expect(client.getQueryState(["presence"])?.status).toBe("success");
    expect(client.getQueryState(["clubs", "me"])).toBeUndefined();
  });

  it("knows every part the server sends", () => {
    expect(Object.keys(HOME_PARTS)).toHaveLength(38);
  });
});
