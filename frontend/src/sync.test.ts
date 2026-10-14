import { describe, expect, it } from "vitest";
import { elapsedSeconds, mmss, progressLine, slowHint, untilText } from "./sync";

describe("progress helpers", () => {
  it("formats minutes and seconds", () => {
    expect(mmss(83)).toBe("1:23");
    expect(mmss(5)).toBe("0:05");
    expect(mmss(-3)).toBe("0:00");
  });
  it("measures elapsed time from the server's zone-less UTC timestamp", () => {
    const now = Date.parse("2026-10-06T21:41:00Z");
    expect(elapsedSeconds("2026-10-06T21:38:27.828332", now)).toBeCloseTo(152.17, 1);
    expect(elapsedSeconds("2026-10-06T21:38:27Z", now)).toBe(153);
    expect(elapsedSeconds(null, now)).toBe(0);
    expect(elapsedSeconds("garbage", now)).toBe(0);
  });
  it("builds the status line", () => {
    expect(progressLine({ stage: "Running the model", step: 1, steps: 2 }, 192)).toBe("Step 1 of 2 · Running the model · 3:12");
    expect(progressLine({ stage: "Running the model", step: 1, steps: 1 }, 4)).toBe("Running the model · 0:04");
    expect(progressLine({ stage: null, step: 0, steps: 0 }, 0)).toBe("Working · 0:00");
  });
  it("only hints at slowness for the model step, and only once it has dragged on", () => {
    const m = { stage: "Running the model", detail: null };
    expect(slowHint(m, 30)).toBeNull();
    expect(slowHint(m, 60)).toContain("small server");
    expect(slowHint({ stage: "Running the model (full recalibration)", detail: null }, 60)).toContain("8 minutes");
    expect(slowHint({ stage: "Fetching odds", detail: null }, 600)).toBeNull();
  });
});


describe("untilText", () => {
  const now = Date.parse("2026-10-13T12:00:00Z");
  it("counts down to the next sync", () => {
    expect(untilText("2026-10-13T12:30:00", now)).toBe("in 30 min");
    expect(untilText("2026-10-13T15:10:00", now)).toBe("in 3 h");
    expect(untilText("2026-10-16T12:00:00", now)).toBe("in 3 d");
    expect(untilText("2026-10-13T11:59:00", now)).toBe("now");
  });
});
