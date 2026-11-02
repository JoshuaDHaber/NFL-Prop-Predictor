import { describe, expect, it, vi } from "vitest";
import { DEFAULTS, changedPrefs, getPrefs, setPrefs, setPrefsSink } from "./prefs";

describe("prefs", () => {
  it("starts at the defaults with no storage, and sends only real changes to the account", () => {
    expect(getPrefs()).toEqual(DEFAULTS);
    const sink = vi.fn();
    setPrefsSink(sink);
    // picking the default sportsbook is a real choice (it's what Best props opens at), so it's sent along
    setPrefs({ theme: "dark", game_book: DEFAULTS.game_book });
    expect(sink).toHaveBeenCalledWith({ theme: "dark", game_book: DEFAULTS.game_book });
    setPrefs({ theme: "dark" });
    expect(sink).toHaveBeenCalledTimes(1);
    // the account's own settings arriving are applied here without being sent back
    setPrefs({ one_per_player: false }, { save: false });
    expect(sink).toHaveBeenCalledTimes(1);
    expect(changedPrefs()).toEqual({ theme: "dark", game_book: DEFAULTS.game_book, one_per_player: false });
    setPrefsSink(null);
  });
});

describe("the board's sportsbook", () => {
  it("is every book until a sportsbook is picked, and picking the default (FanDuel) still counts", async () => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) });
    vi.resetModules();
    const prefs = await import("./prefs");
    expect(prefs.chosenGameBook()).toBeNull();
    prefs.setPrefs({ game_book: "FanDuel" });
    expect(prefs.chosenGameBook()).toBe("FanDuel");
    prefs.setPrefs({ game_book: "DraftKings" });
    expect(prefs.chosenGameBook()).toBe("DraftKings");
    expect(prefs.changedPrefs()).toMatchObject({ game_book: "DraftKings" });
    vi.unstubAllGlobals();
  });
});
