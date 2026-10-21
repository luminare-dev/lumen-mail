import { describe, expect, it } from "vitest";
import { contrast, formatRatio, luminance, parseHex } from "../src/contrast";

describe("contrast", () => {
  it("parses short and long hex colours", () => {
    expect(parseHex("#fff")).toEqual([255, 255, 255]);
    expect(parseHex("0A1224")).toEqual([10, 18, 36]);
    expect(parseHex("not a colour")).toBeNull();
    expect(luminance("xyz")).toBeNaN();
    expect(parseHex("bad")).toEqual([187, 170, 221]); // "bad" is a valid short hex colour
  });

  it("matches the WCAG reference values", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
    // #767676 on white is the classic 4.54:1
    expect(contrast("#767676", "#FFFFFF")).toBeCloseTo(4.54, 2);
    expect(contrast("#FFFFFF", "#767676")).toBe(contrast("#767676", "#FFFFFF"));
  });

  it("rounds down, so a ratio just under a limit never looks like a pass", () => {
    expect(formatRatio(4.499)).toBe("4.49:1");
    expect(formatRatio(21)).toBe("21.00:1");
  });

  it("agrees with docs/contrast.md for a Lumen pair (night text on mist)", () => {
    expect(formatRatio(contrast("#0A1224", "#F3F6FB"))).toBe("17.23:1");
  });
});
