// Fuzzy matching for the command palette. No dependencies, no DOM.
//
// A query matches a text when its characters appear in order (a subsequence). The score prefers
// matches at the start of the text and of words, and runs of consecutive characters; gaps and
// long texts cost a little. Case and accents are ignored: "entwurfe" finds "Entwürfe".

import type { Match, Searchable } from "./types";

/** Lower case without diacritics, one output character per input character ("Ü" -> "u"). */
export function fold(text: string): string {
  let out = "";
  for (const ch of String(text)) {
    const base = ch.normalize("NFD").replace(/\p{M}+/gu, "");
    out += (base.length === 1 ? base : ch).toLowerCase();
  }
  return out;
}

const WORD_START = /[\s\-_/.,:;()[\]|&]/u;

export interface TokenScore {
  score: number;
  indices: number[];
}

/** Score one query token against one text: null if it does not match. */
export function scoreToken(token: string, text: string): TokenScore | null {
  const q = Array.from(fold(token));
  const t = Array.from(fold(text));
  if (q.length === 0) return { score: 0, indices: [] };
  const indices: number[] = [];
  let score = 0;
  let qi = 0;
  let prev = -2;
  for (let i = 0; i < t.length && qi < q.length; i += 1) {
    if (t[i] !== q[qi]) continue;
    let s = 1;
    if (i === 0) s += 8;
    else if (WORD_START.test(t[i - 1] ?? "")) s += 6;
    if (i === prev + 1) s += 4;
    else if (prev >= 0) s -= Math.min(3, (i - prev - 1) * 0.25);
    score += s;
    indices.push(i);
    prev = i;
    qi += 1;
  }
  if (qi < q.length) return null;
  // A plain substring beats a scattered match; shorter texts win ties.
  if (t.join("").includes(q.join(""))) score += 5;
  score -= t.length * 0.02;
  return { score, indices };
}

/**
 * Rank entries for a query. Every whitespace-separated token must match the label, the detail
 * or the group; label matches count fully, the others half. Without a query the entries keep
 * their order.
 */
export function search<T extends Searchable>(entries: readonly T[], query: string, limit = 50): Match<T>[] {
  const tokens = String(query).trim().split(/\s+/u).filter(Boolean);
  if (tokens.length === 0) return entries.slice(0, limit).map((entry) => ({ entry, score: 0, indices: [] }));
  const results: Match<T>[] = [];
  for (const entry of entries) {
    let total = 0;
    const indices = new Set<number>();
    let ok = true;
    for (const token of tokens) {
      const inLabel = scoreToken(token, entry.label);
      let other = 0;
      for (const text of [entry.detail, entry.group]) {
        const s = text ? scoreToken(token, text) : null;
        if (s) other = Math.max(other, s.score / 2);
      }
      if (inLabel && inLabel.score >= other) {
        total += inLabel.score;
        for (const i of inLabel.indices) indices.add(i);
      } else if (other > 0) {
        total += other;
      } else {
        ok = false;
        break;
      }
    }
    if (ok) results.push({ entry, score: total, indices: [...indices].sort((a, b) => a - b) });
  }
  results.sort((a, b) => b.score - a.score || a.entry.label.length - b.entry.label.length);
  return results.slice(0, limit);
}

export interface Part {
  text: string;
  hit: boolean;
}

/** Split a label into runs of matched and unmatched characters, for highlighting. */
export function highlight(label: string, indices: readonly number[]): Part[] {
  const hits = new Set(indices);
  const parts: Part[] = [];
  Array.from(label).forEach((ch, i) => {
    const hit = hits.has(i);
    const last = parts[parts.length - 1];
    if (last && last.hit === hit) last.text += ch;
    else parts.push({ text: ch, hit });
  });
  return parts;
}
