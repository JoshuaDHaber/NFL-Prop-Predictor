import { describe, expect, it, vi } from "vitest";

// node has no localStorage: a small one, so a browser that saved the old admin password can be imitated
const store = new Map<string, string>([["nfl-props-admin-token", "hunter2"]]);
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
});

describe("the retired admin password", () => {
  it("is forgotten by any browser that saved one", async () => {
    expect(store.has("nfl-props-admin-token")).toBe(true);
    await import("./auth");
    expect(store.has("nfl-props-admin-token")).toBe(false);
  });
});
