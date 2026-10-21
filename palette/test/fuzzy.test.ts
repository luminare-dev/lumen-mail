import { describe, expect, it } from "vitest";
import { fold, highlight, scoreToken, search } from "../src/fuzzy";

const ENTRIES = [
  { label: "Compose", group: "Actions" },
  { label: "Settings", group: "Go to" },
  { label: "Sent", group: "Folders" },
  { label: "Junk", group: "Folders" },
  { label: "2024", group: "Folders", detail: "Archive" },
  { label: "Archive", group: "Folders" },
  { label: "Entwürfe alt", group: "Ordner" },
  { label: "Mailbox View", group: "Settings", detail: "Preferences" },
];
const labels = (query: string) => search(ENTRIES, query).map((m) => m.entry.label);

describe("fold", () => {
  it("lower-cases and drops accents, one character per character", () => {
    expect(fold("Entwürfe ÄÖÜ")).toBe("entwurfe aou");
    expect(fold("Ǆ")).toHaveLength(1);
  });
});

describe("scoreToken", () => {
  it("matches subsequences and rejects anything else", () => {
    expect(scoreToken("jnk", "Junk")).not.toBeNull();
    expect(scoreToken("knj", "Junk")).toBeNull();
    expect(scoreToken("j", "Junk")?.indices).toEqual([0]);
  });

  it("prefers the start of the text and of words over scattered matches", () => {
    const start = scoreToken("se", "Sent")!.score;
    const word = scoreToken("vi", "Mailbox View")!.score;
    const scattered = scoreToken("se", "Mailbox View settings")!.score;
    expect(start).toBeGreaterThan(scattered);
    expect(word).toBeGreaterThan(scoreToken("ie", "Mailbox View")!.score);
  });
});

describe("search", () => {
  it("keeps the given order without a query and honours the limit", () => {
    expect(labels("")).toEqual(ENTRIES.map((e) => e.label));
    expect(search(ENTRIES, "   ", 2)).toHaveLength(2);
  });

  it("ranks prefix matches first", () => {
    expect(labels("se").slice(0, 2)).toEqual(["Sent", "Settings"]);
    expect(labels("com")[0]).toBe("Compose");
  });

  it("finds accented names without accents and in any case", () => {
    expect(labels("ENTWURFE")).toEqual(["Entwürfe alt"]);
  });

  it("matches the detail and the group at half weight, after label matches", () => {
    const archive = labels("archive");
    expect(archive[0]).toBe("Archive");
    expect(archive).toContain("2024");
    expect(labels("preferences mailbox")).toEqual(["Mailbox View"]);
  });

  it("needs every token to match somewhere", () => {
    expect(labels("sent zzz")).toEqual([]);
  });

  it("reports the matched label positions for highlighting", () => {
    const [first] = search(ENTRIES, "cmp");
    expect(first?.entry.label).toBe("Compose");
    expect(first?.indices).toEqual([0, 2, 3]);
  });
});

describe("highlight", () => {
  it("splits a label into matched and unmatched runs", () => {
    expect(highlight("Compose", [0, 2, 3])).toEqual([
      { text: "C", hit: true },
      { text: "o", hit: false },
      { text: "mp", hit: true },
      { text: "ose", hit: false },
    ]);
    expect(highlight("Inbox", [])).toEqual([{ text: "Inbox", hit: false }]);
  });
});
