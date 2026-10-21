// Types of the command palette, and the part of Roundcube's client API (window.rcmail, see
// program/js/app.js) it uses. Nothing else of Roundcube is touched.

/** One folder in rcmail.env.mailboxes (set by Roundcube's folder list in the mail task). */
export interface Mailbox {
  /** The IMAP folder name (UTF7-IMAP), used for commands and as the key. */
  id: string;
  /** The display name of the last level, already decoded and localized by Roundcube. */
  name: string;
  /** A folder that only groups others and cannot be opened. */
  virtual?: boolean;
  level?: number;
}

export interface RcmailEnv {
  skin?: string;
  task?: string;
  action?: string;
  framed?: unknown;
  extwin?: unknown;
  server_error?: unknown;
  mailbox?: string;
  mailboxes?: Record<string, Mailbox>;
  mailboxes_list?: string[];
  delimiter?: string;
}

/** The subset of rcube_webmail the palette calls. */
export interface Rcmail {
  env: RcmailEnv;
  commands?: Record<string, unknown>;
  command: (command: string, props?: unknown) => unknown;
  get_label?: (label: string, domain?: string) => string;
  sections_list?: { select?: (id: string) => void } | null;
}

export type Kind = "action" | "task" | "folder" | "setting";

/** One thing the palette offers. Labels are plain text; React renders them as text nodes. */
export interface Item {
  /** Unique within one collection, e.g. "folder:INBOX". */
  id: string;
  kind: Kind;
  label: string;
  /** The group shown next to the label (Actions, Go to, Folders, Settings). */
  group: string;
  /** Extra context after the label, e.g. a folder's parent folders. */
  detail?: string;
  /** The item is the task, folder or section on screen now. */
  current?: boolean;
  /** Runs the item through Roundcube's own API (a command or its own button). */
  run: () => void;
}

/** What fuzzy search reads from an item. */
export interface Searchable {
  label: string;
  group?: string;
  detail?: string;
}

export interface Match<T extends Searchable> {
  entry: T;
  score: number;
  /** Positions of the matched characters in `entry.label` (code points). */
  indices: number[];
}
