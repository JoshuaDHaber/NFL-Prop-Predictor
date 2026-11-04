import { describe, expect, it } from "vitest";
import { lockScroll } from "./Sheet";

describe("lockScroll", () => {
  it("unlocks the page only when the last panel closes, in any order", () => {
    const body = { style: { overflow: "" } };
    (globalThis as unknown as { document: unknown }).document = { body };
    const slip = lockScroll();
    const track = lockScroll();   // the Track sheet over the slip
    expect(body.style.overflow).toBe("hidden");
    slip();                        // "See My bets" closes the slip first...
    expect(body.style.overflow).toBe("hidden");
    track();                       // ...then the sheet on top: the page scrolls again
    expect(body.style.overflow).toBe("");
  });
});
