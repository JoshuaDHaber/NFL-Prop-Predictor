import { describe, expect, it } from "vitest";
import { loadShapes, stateAt } from "./geoState";

describe("stateAt", () => {
  it("finds the state for a coordinate", async () => {
    const shapes = await loadShapes();
    expect(stateAt(-74.17, 40.73, shapes)).toBe("NJ");   // Newark
    expect(stateAt(-73.99, 40.75, shapes)).toBe("NY");   // Manhattan
    expect(stateAt(-75.16, 39.95, shapes)).toBe("PA");   // Philadelphia
    expect(stateAt(-77.04, 38.90, shapes)).toBe("DC");
    expect(stateAt(-157.86, 21.31, shapes)).toBe("HI");  // Honolulu
    expect(stateAt(-87.63, 41.88, shapes)).toBe("IL");   // Chicago
  });

  it("returns null outside the US", async () => {
    const shapes = await loadShapes();
    expect(stateAt(-79.38, 43.65, shapes)).toBeNull();   // Toronto
    expect(stateAt(-40, 30, shapes)).toBeNull();          // Atlantic
  });
});
