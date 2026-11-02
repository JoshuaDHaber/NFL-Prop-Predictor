import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// node has no localStorage: a small one, so the saved admin password can be watched
const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
});

const { getToken, setToken, signOut } = await import("./auth");
const signedOut = { user: null, google: true };

describe("signOut", () => {
  beforeEach(() => setToken("hunter2"));
  afterEach(() => vi.unstubAllGlobals());

  it("forgets the saved admin password along with the account", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(signedOut), { status: 200 })));
    expect(getToken()).toBe("hunter2");
    await signOut();
    expect(getToken()).toBe("");
  });

  it("forgets it even when the server can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(signOut()).rejects.toThrow();
    expect(getToken()).toBe("");
  });
});
