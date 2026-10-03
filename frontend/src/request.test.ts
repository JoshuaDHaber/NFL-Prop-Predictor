import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// api.ts reads VITE_API_URL when it loads, so each test sets it first and imports a fresh copy
async function load(apiUrl: string) {
  vi.resetModules();
  vi.stubEnv("VITE_API_URL", apiUrl);
  const auth = await import("./auth");
  const api = await import("./api");
  return { ...api, ...auth };
}

const res = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  vi.useFakeTimers();
  let store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { store = {}; },
  });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("request against a hosted API", () => {
  it("retries reads while the host wakes up, then returns the answer", async () => {
    const { request } = await load("https://api.example.com/");
    const fetchMock = vi.fn().mockResolvedValueOnce(res(503)).mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue(res(200, { ok: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    const p = request("/api/meta");
    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(3000);
    expect((await p).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.com/api/meta"); // trailing slash trimmed
  });

  it("never retries a write, since it can spend API credits", async () => {
    const { request } = await load("https://api.example.com");
    const fetchMock = vi.fn().mockResolvedValue(res(503));
    vi.stubGlobal("fetch", fetchMock);
    expect((await request("/api/refresh", { method: "POST" })).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends the admin token as a Bearer header", async () => {
    const { request, setToken } = await load("https://api.example.com");
    setToken("s3cret");
    const fetchMock = vi.fn().mockResolvedValue(res(200));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/meta");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer s3cret");
  });

  it("gives up after the wake window instead of retrying forever", async () => {
    const { request } = await load("https://api.example.com");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const p = request("/api/meta").catch((e) => e);
    await vi.advanceTimersByTimeAsync(3000 * 30);
    expect(await p).toBeInstanceOf(TypeError);
  });
});

describe("request against the same origin (local app)", () => {
  it("does not retry or add a token", async () => {
    const { request, setToken } = await load("");
    setToken("ignored");
    const fetchMock = vi.fn().mockResolvedValue(res(503));
    vi.stubGlobal("fetch", fetchMock);
    expect((await request("/api/meta")).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });
});
