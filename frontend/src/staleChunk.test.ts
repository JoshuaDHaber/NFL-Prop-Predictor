import { beforeEach, describe, expect, it, vi } from "vitest";
import { importOrReload } from "./staleChunk";

const store: Record<string, string> = {};
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k];
  vi.stubGlobal("sessionStorage", { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v; } });
});

describe("importOrReload", () => {
  it("passes a successful import through", async () => {
    const reload = vi.fn();
    await expect(importOrReload(() => Promise.resolve("ok"), reload)).resolves.toBe("ok");
    expect(reload).not.toHaveBeenCalled();
  });
  it("reloads once when a file from an old build is gone", () => {
    const reload = vi.fn();
    importOrReload(() => Promise.reject(new Error("Failed to fetch dynamically imported module")), reload, 1_000_000);
    return new Promise<void>((done) => setTimeout(() => { expect(reload).toHaveBeenCalledTimes(1); done(); }, 0));
  });
  it("gives up instead of looping when it already reloaded moments ago", async () => {
    store["stale-chunk-reload-at"] = "1000000";
    const reload = vi.fn();
    await expect(importOrReload(() => Promise.reject(new Error("gone")), reload, 1_010_000)).rejects.toThrow("gone");
    expect(reload).not.toHaveBeenCalled();
  });
});
