import { describe, expect, it, vi } from "vitest";
import { DEFAULTS, changedPrefs, getPrefs, setPrefs, setPrefsSink } from "./prefs";

describe("prefs", () => {
  it("starts at the defaults with no storage, and sends only real changes to the account", () => {
    expect(getPrefs()).toEqual(DEFAULTS);
    const sink = vi.fn();
    setPrefsSink(sink);
    setPrefs({ theme: "dark", game_book: DEFAULTS.game_book });
    expect(sink).toHaveBeenCalledWith({ theme: "dark" });
    setPrefs({ theme: "dark" });
    expect(sink).toHaveBeenCalledTimes(1);
    // the account's own settings arriving are applied here without being sent back
    setPrefs({ one_per_player: false }, { save: false });
    expect(sink).toHaveBeenCalledTimes(1);
    expect(changedPrefs()).toEqual({ theme: "dark", one_per_player: false });
    setPrefsSink(null);
  });
});
