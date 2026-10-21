// The command palette: a modal dialog with a search field and a list of folders, settings and
// actions.
//
// Accessibility: role="dialog" with aria-modal; the search field is a combobox that controls a
// listbox and points at the highlighted option with aria-activedescendant, so focus stays in the
// field while the arrow keys move through the results. Tab and Shift+Tab cycle between the field
// and the close button (focus trap); focus that escapes (a click, a script) is brought back.
// Closing returns focus to where it was before the palette opened.

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { collect } from "./collect";
import { highlight, search } from "./fuzzy";
import { translator } from "./i18n";
import { deepActiveElement, inEditor, isApplePlatform, isToggleKey, usePageState, type NavigatorLike } from "./page";
import type { Item, Rcmail } from "./types";

const PAGE_STEP = 8;
const MAX_RESULTS = 50;

function SearchIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="m16 16 4.5 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export interface PaletteProps {
  rc: Rcmail;
  doc?: Document;
  /** The visible trigger (a link in Elastic's task menu), if there is one. */
  trigger?: HTMLElement | null;
  /** Reads the items each time the palette opens (default: collect() from rcmail and the page). */
  getItems?: (rc: Rcmail, doc: Document, t: ReturnType<typeof translator>) => Item[];
}

export function Palette({ rc, doc = document, trigger = null, getItems = collect }: PaletteProps) {
  const page = usePageState(doc);
  const t = useMemo(() => translator(rc), [rc]);
  const apple = useMemo(() => isApplePlatform(doc.defaultView?.navigator as NavigatorLike | undefined), [doc]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [items, setItems] = useState<Item[]>([]);
  const openRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const returnFocus = useRef<Element | null>(null);
  const uid = `lmp${useId().replace(/[^A-Za-z0-9_-]/gu, "")}`;
  const ids = { title: `${uid}-title`, list: `${uid}-list`, status: `${uid}-status`, hint: `${uid}-hint` };

  const results = useMemo(() => search(items, query, query.trim() ? MAX_RESULTS : Infinity), [items, query]);
  const count = results.length;
  const current = Math.min(active, Math.max(count - 1, 0));

  const show = useCallback(
    (from?: Element | null) => {
      returnFocus.current = from ?? deepActiveElement(doc);
      openRef.current = true;
      let list: Item[] = [];
      try {
        list = getItems(rc, doc, t);
      } catch (error) {
        console.warn("lumen: could not read the palette items", error);
      }
      setItems(list);
      setQuery("");
      setActive(0);
      setOpen(true);
    },
    [doc, getItems, rc, t],
  );

  const hide = useCallback(() => {
    openRef.current = false;
    setOpen(false);
    const el = returnFocus.current;
    returnFocus.current = null;
    if (el && "focus" in el && el.isConnected) (el as HTMLElement).focus();
  }, []);

  const run = useCallback(
    (item: Item | undefined) => {
      if (!item) return;
      hide();
      try {
        item.run();
      } catch (error) {
        console.warn("lumen: palette item failed", error);
      }
    },
    [hide],
  );

  const toggle = useCallback(
    (from?: Element | null) => {
      if (openRef.current) hide();
      else show(from);
    },
    [hide, show],
  );

  // Ctrl+K / Cmd+K on the page and in same-origin frames (message preview, settings forms),
  // except while the focus is in a text editor.
  useEffect(() => {
    const win = doc.defaultView;
    if (!win) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.isComposing || !isToggleKey(event, apple) || inEditor(event)) return;
      event.preventDefault();
      event.stopPropagation();
      toggle();
    };
    const watched = new Set<Window>();
    const watch = (frame: Window | null) => {
      if (!frame || watched.has(frame)) return;
      try {
        frame.addEventListener("keydown", onKey, true);
        watched.add(frame);
      } catch {
        // a frame from another origin: its keys stay its own
      }
    };
    const onLoad = (event: Event) => {
      const target = event.target as HTMLIFrameElement | null;
      if (target?.tagName === "IFRAME") watch(target.contentWindow);
    };
    watch(win);
    for (const frame of doc.querySelectorAll("iframe")) watch(frame.contentWindow);
    doc.addEventListener("load", onLoad, true);
    return () => {
      doc.removeEventListener("load", onLoad, true);
      for (const w of watched) {
        try {
          w.removeEventListener("keydown", onKey, true);
        } catch {
          // the frame is gone
        }
      }
    };
  }, [doc, apple, toggle]);

  // The trigger in Elastic's menu: click, Enter (native) and Space (a link with role="button").
  useEffect(() => {
    if (!trigger) return undefined;
    const onClick = (event: Event) => {
      event.preventDefault();
      toggle(trigger);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === " ") {
        event.preventDefault();
        toggle(trigger);
      }
    };
    trigger.addEventListener("click", onClick);
    trigger.addEventListener("keydown", onKeyDown);
    return () => {
      trigger.removeEventListener("click", onClick);
      trigger.removeEventListener("keydown", onKeyDown);
    };
  }, [trigger, toggle]);

  useEffect(() => {
    trigger?.setAttribute("aria-expanded", String(open));
  }, [trigger, open]);

  // The page behind the dialog does not scroll while it is open.
  useEffect(() => {
    if (!open) return undefined;
    const style = doc.documentElement.style;
    const before = style.getPropertyValue("overflow");
    style.setProperty("overflow", "hidden");
    return () => style.setProperty("overflow", before);
  }, [open, doc]);

  // Focus moves into the dialog on open, and back into it if anything moves it out.
  useEffect(() => {
    if (!open) return undefined;
    inputRef.current?.focus();
    const onFocusIn = (event: FocusEvent) => {
      const dialog = dialogRef.current;
      if (!openRef.current || !dialog || event.composedPath().includes(dialog)) return;
      inputRef.current?.focus();
    };
    doc.addEventListener("focusin", onFocusIn, true);
    return () => doc.removeEventListener("focusin", onFocusIn, true);
  }, [open, doc]);

  useEffect(() => {
    const option = listRef.current?.querySelector(`[data-index="${current}"]`);
    if (option && typeof option.scrollIntoView === "function") option.scrollIntoView({ block: "nearest" });
  }, [current, results]);

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    // Keys typed here belong to the palette, not to Roundcube's own keyboard handlers.
    event.stopPropagation();
    // While an input method composes (pinyin, kana), Enter and Escape belong to it.
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    const move = (to: number) => {
      event.preventDefault();
      if (count) setActive(to);
    };
    switch (event.key) {
      case "ArrowDown":
        move((current + 1) % Math.max(count, 1));
        break;
      case "ArrowUp":
        move((current - 1 + count) % Math.max(count, 1));
        break;
      case "PageDown":
        move(Math.min(current + PAGE_STEP, count - 1));
        break;
      case "PageUp":
        move(Math.max(current - PAGE_STEP, 0));
        break;
      case "Home":
      case "End":
        if (event.ctrlKey) move(event.key === "Home" ? 0 : count - 1);
        break;
      case "Enter":
        if (event.target !== inputRef.current) break; // the close button handles its own Enter
        event.preventDefault();
        run(results[current]?.entry);
        break;
      case "Escape":
        event.preventDefault();
        hide();
        break;
      case "Tab": {
        const stops = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("input, button") ?? []);
        if (stops.length === 0) break;
        event.preventDefault();
        const at = stops.indexOf(event.target as HTMLElement);
        const next = event.shiftKey ? (at <= 0 ? stops.length - 1 : at - 1) : (at + 1) % stops.length;
        stops[next]?.focus();
        break;
      }
      default:
        break;
    }
  };

  // A click on the dialog's text must not take the focus away from the search field.
  const keepFocus = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.target !== inputRef.current) event.preventDefault();
  };

  if (!open) return null;

  const close = t("close");
  return (
    <div className={page.dark ? "lm is-dark" : "lm"} dir={page.dir} lang={page.lang}>
      <div
        className="backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) hide();
        }}
      >
        <div
          ref={dialogRef}
          className="dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={ids.title}
          onKeyDown={onKeyDown}
          onMouseDown={keepFocus}
        >
          <h2 id={ids.title} className="visually-hidden">
            {t("palette_title")}
          </h2>
          <div className="search">
            <SearchIcon />
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-expanded="true"
              aria-controls={ids.list}
              aria-autocomplete="list"
              aria-activedescendant={count ? `${uid}-opt-${current}` : undefined}
              aria-describedby={`${ids.status} ${ids.hint}`}
              aria-label={t("palette_placeholder")}
              placeholder={t("palette_placeholder")}
              autoComplete="off"
              spellCheck={false}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
              }}
            />
            <button type="button" className="close" aria-label={`${close} (Esc)`} title={close} onClick={hide}>
              <kbd aria-hidden="true">Esc</kbd>
            </button>
          </div>
          <ul id={ids.list} ref={listRef} className="results" role="listbox" aria-label={t("palette_title")}>
            {results.map(({ entry, indices }, index) => (
              <li
                key={entry.id}
                id={`${uid}-opt-${index}`}
                data-index={index}
                data-kind={entry.kind}
                role="option"
                aria-selected={index === current}
                className={index === current ? "option is-active" : "option"}
                onMouseMove={() => index !== current && setActive(index)}
                onClick={() => run(entry)}
              >
                <span className="label">
                  {highlight(entry.label, indices).map((part, i) =>
                    part.hit ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>,
                  )}
                </span>
                {/* Each extra is one hidden ", text" string, so screen readers hear the whole
                    option as one name; the visible parts are hidden from them instead. */}
                {entry.detail && (
                  <>
                    <span className="detail" aria-hidden="true">
                      {entry.detail}
                    </span>
                    <span className="visually-hidden">{`, ${entry.detail}`}</span>
                  </>
                )}
                {entry.current && (
                  <>
                    <span className="badge" aria-hidden="true">
                      {t("palette_current")}
                    </span>
                    <span className="visually-hidden">{`, ${t("palette_current")}`}</span>
                  </>
                )}
                <span className="group" aria-hidden="true">
                  {entry.group}
                </span>
                <span className="visually-hidden">{`, ${entry.group}`}</span>
              </li>
            ))}
          </ul>
          {count === 0 && <p className="empty">{t("palette_empty")}</p>}
          <p id={ids.status} className="visually-hidden" role="status" aria-live="polite">
            {t("palette_results", { n: count })}
          </p>
          <p id={ids.hint} className="hint">
            {t("palette_hint")}
          </p>
        </div>
      </div>
    </div>
  );
}
