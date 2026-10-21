// The gallery page: design tokens with live contrast numbers, type, shape and motion, the real
// command palette on a mocked rcmail, and previews of the skin (when a built skin was given).

import data from "virtual:lumen-gallery";
import { useEffect, useMemo, useState } from "react";
import { isApplePlatform, type NavigatorLike } from "../../palette/src/page";
import lockupUrl from "../../skin/images/luminare-lockup-horizontal-dark.svg?url";
import { contrast, formatRatio } from "./contrast";
import type { Lang } from "./mock";

type Mode = "light" | "dark";
const { tokens, pairs } = data;

/** --lm-* custom properties for both modes, as the skin's stylesheet defines them. */
export function tokenCss(): string {
  const props = (mode: Mode) => tokens.roles.map((r) => `--lm-${r}: ${tokens[mode][r]};`).join(" ");
  const shape = Object.entries(tokens.shape)
    .filter(([name]) => /^(font|font-mono|radius-[a-z]+|ring|duration|ease)$/u.test(name))
    .map(([name, value]) => `--lm-${name}: ${value};`)
    .join(" ");
  return `:root { ${shape} ${props("light")} --lm-shadow-2: 0 12px 32px rgb(10 18 36 / 12%); }
:root.dark-mode { ${props("dark")} --lm-shadow-2: 0 16px 40px rgb(0 0 0 / 45%); }`;
}

function Toggle({ label, options, value, onChange }: {
  label: string;
  options: [string, string][];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className="toggle">
      <legend>{label}</legend>
      {options.map(([v, text]) => (
        <label key={v} className={v === value ? "is-on" : undefined}>
          <input type="radio" name={label} value={v} checked={v === value} onChange={() => onChange(v)} />
          {text}
        </label>
      ))}
    </fieldset>
  );
}

function Swatches({ mode }: { mode: Mode }) {
  return (
    <div className="swatches" data-mode={mode}>
      {tokens.roles.map((role) => {
        const value = tokens[mode][role] ?? "";
        const onBg = contrast(value, tokens[mode].bg ?? "#FFFFFF");
        return (
          <figure key={role} className="swatch">
            <span className="chip" style={{ background: value }} />
            <figcaption>
              <code>--lm-{role}</code>
              <span>
                {value} · {formatRatio(onBg)} on bg
              </span>
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}

function ContrastTable() {
  let failures = 0;
  const rows = pairs.map((p, i) => {
    const cells = (["light", "dark"] as const).map((mode) => {
      const fg = tokens[mode][p.fg] ?? "";
      const bg = tokens[mode][p.bg] ?? "";
      const ratio = contrast(fg, bg);
      const ok = ratio >= p.min;
      if (!ok) failures += 1;
      return (
        <td key={mode} className={ok ? "pass" : "fail"}>
          <span className="sample" style={{ color: fg, background: bg }}>
            Aa
          </span>{" "}
          {formatRatio(ratio)} <span className="verdict">{ok ? "pass" : "FAIL"}</span>
        </td>
      );
    });
    return (
      <tr key={i}>
        <th scope="row">
          <code>{p.fg}</code> on <code>{p.bg}</code>
        </th>
        <td>{p.use}</td>
        <td>{p.min.toFixed(1)}:1</td>
        {cells}
      </tr>
    );
  });
  return (
    <>
      <p className="lead">
        {pairs.length} pairs × 2 modes, computed here from the tokens with the WCAG 2.2 formula:{" "}
        <strong>{failures === 0 ? "all pass" : `${failures} fail`}</strong>. Text needs 4.5:1, UI parts 3:1.
        scripts/contrast.py checks the same pairs in CI and writes docs/contrast.md.
      </p>
      <div className="table-scroll">
        <table className="pairs">
          <thead>
            <tr>
              <th scope="col">Pair</th>
              <th scope="col">Used for</th>
              <th scope="col">Minimum</th>
              <th scope="col">Light</th>
              <th scope="col">Dark</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </>
  );
}

function Typography() {
  const sizes: [string, number, number][] = [
    ["Display", 32, 600],
    ["Title", 24, 600],
    ["Heading", 20, 600],
    ["Body", 15, 400],
    ["List row", 14, 400],
    ["Label", 13, 500],
    ["Rail label", 12, 500],
  ];
  return (
    <div className="type-scale">
      {sizes.map(([name, size, weight]) => (
        <p key={name} style={{ fontSize: size, fontWeight: weight }}>
          <span className="meta">
            {name} · {size}px · {weight}
          </span>
          Calm, clear mail for every inbox
        </p>
      ))}
    </div>
  );
}

function Shape() {
  const radii = Object.entries(tokens.shape).filter(([n]) => n.startsWith("radius-") && n !== "radius-pill");
  const space = Object.entries(tokens.shape).filter(([n]) => n.startsWith("space-"));
  return (
    <div className="shape">
      <div className="radii">
        {radii.map(([name, value]) => (
          <figure key={name}>
            <span className="box" style={{ borderRadius: value }} />
            <figcaption>
              <code>{name}</code> {value}
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="spacing">
        {space.map(([name, value]) => (
          <figure key={name}>
            <span className="bar" style={{ inlineSize: value }} />
            <figcaption>
              <code>{name}</code> {value}
            </figcaption>
          </figure>
        ))}
      </div>
      <p>
        Focus ring <code>{tokens.shape.ring}</code> in <code>--lm-focus</code>; motion{" "}
        <code>{tokens.shape.duration}</code> <code>{tokens.shape.ease}</code>, off with prefers-reduced-motion.{" "}
        <button type="button" className="demo-button">
          Tab to me
        </button>
      </p>
    </div>
  );
}

function PaletteDemo() {
  const [last, setLast] = useState<string>("");
  useEffect(() => {
    const on = (event: Event) => {
      const { name, props } = (event as CustomEvent<{ name: string; props?: unknown }>).detail;
      setLast(`rcmail.command(${JSON.stringify(name)}${props === undefined ? "" : `, ${JSON.stringify(props)}`})`);
    };
    window.addEventListener("lumen-gallery-command", on);
    return () => window.removeEventListener("lumen-gallery-command", on);
  }, []);
  const apple = isApplePlatform(navigator as NavigatorLike);
  const open = () =>
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", code: "KeyK", ctrlKey: !apple, metaKey: apple }));
  return (
    <div className="palette-demo">
      <p>
        The real palette bundle code on a mocked <code>rcmail</code> (mail task, 13 folders, every command enabled).
        Press <kbd>{apple ? "⌘ K" : "Ctrl K"}</kbd> anywhere on this page, or:
      </p>
      <p>
        <button type="button" className="demo-button primary" onClick={open}>
          Open the command palette
        </button>
      </p>
      <p className="log" role="status">
        {last ? (
          <>
            Last item: <code>{last}</code> (not run in the gallery)
          </>
        ) : (
          "Pick an item to see the Roundcube command it runs."
        )}
      </p>
    </div>
  );
}

function Previews({ mode, dir }: { mode: Mode; dir: string }) {
  const [width, setWidth] = useState("1280");
  if (!data.skin) {
    return (
      <p className="note">
        No built skin was given, so the skin previews are off. Build the skin, then start or build the gallery with{" "}
        <code>LUMEN_GALLERY_SKINS=&lt;roundcube&gt;/skins</code> (a folder with <code>lumen/</code> and{" "}
        <code>elastic/</code>); see docs/development.md.
      </p>
    );
  }
  return (
    <>
      <p className="lead">
        Built skin: Lumen {data.skin.lumenVersion} for Roundcube {data.skin.roundcubeVersion}, {data.skin.builtAt}.
        Markup written for the gallery with Elastic's ids and classes; Elastic's scripts do not run here.
      </p>
      <Toggle label="Width" options={[["1280", "1280 px"], ["360", "360 px"]]} value={width} onChange={setWidth} />
      <div className="previews">
        {["mail", "settings", "login"].map((page) => (
          <figure key={page} className="preview">
            <figcaption>{page}</figcaption>
            <div className="frame-scroll">
              <iframe
                title={`${page} preview (${mode}, ${dir})`}
                src={`preview.html?page=${page}&mode=${mode}&dir=${dir}`}
                style={{ inlineSize: `${width}px` }}
                loading="lazy"
              />
            </div>
          </figure>
        ))}
      </div>
    </>
  );
}

export function App({ setLang }: { setLang: (lang: Lang) => void }) {
  const prefersDark = useMemo(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false, []);
  const [mode, setMode] = useState<Mode>(prefersDark ? "dark" : "light");
  const [dir, setDir] = useState("ltr");
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("dark-mode", mode === "dark");
    html.setAttribute("dir", dir);
    html.setAttribute("lang", lang);
    setLang(lang);
  }, [mode, dir, lang, setLang]);

  return (
    <>
      <style>{tokenCss()}</style>
      <header className="top">
        <img className="lockup" src={lockupUrl} alt="Luminare" height="36" />
        <div>
          <h1>Lumen gallery</h1>
          <p>
            The design system of Lumen {data.version}, a modern Luminare skin for Roundcube Webmail.
          </p>
        </div>
        <div className="controls">
          <Toggle label="Mode" options={[["light", "Light"], ["dark", "Dark"]]} value={mode} onChange={(v) => setMode(v as Mode)} />
          <Toggle label="Direction" options={[["ltr", "LTR"], ["rtl", "RTL"]]} value={dir} onChange={setDir} />
          <Toggle label="Language" options={[["en", "English"], ["de", "Deutsch"]]} value={lang} onChange={(v) => setLangState(v as Lang)} />
        </div>
      </header>
      <nav className="toc" aria-label="Sections">
        <a href="#colours">Colours</a> <a href="#contrast">Contrast</a> <a href="#type">Type</a>{" "}
        <a href="#shape">Shape</a> <a href="#palette">Command palette</a> <a href="#previews">Skin previews</a>
      </nav>
      <main>
        <section id="colours" aria-labelledby="h-colours">
          <h2 id="h-colours">Colour roles</h2>
          <p className="lead">Each role is a --lm-* custom property; html.dark-mode (Elastic's class) switches the set.</p>
          <Swatches mode={mode} />
        </section>
        <section id="contrast" aria-labelledby="h-contrast">
          <h2 id="h-contrast">Contrast</h2>
          <ContrastTable />
        </section>
        <section id="type" aria-labelledby="h-type">
          <h2 id="h-type">Typography: Sora</h2>
          <Typography />
        </section>
        <section id="shape" aria-labelledby="h-shape">
          <h2 id="h-shape">Shape, space and motion</h2>
          <Shape />
        </section>
        <section id="palette" aria-labelledby="h-palette">
          <h2 id="h-palette">Command palette</h2>
          <PaletteDemo />
        </section>
        <section id="previews" aria-labelledby="h-previews">
          <h2 id="h-previews">Skin previews</h2>
          <Previews mode={mode} dir={dir} />
        </section>
      </main>
      <footer className="bottom">
        <p>
          <em>a Luminare Development open-source project</em> · MIT ·{" "}
          <a href="https://github.com/luminare-dev/lumen-mail">github.com/luminare-dev/lumen-mail</a>
        </p>
        <p>
          Not affiliated with or endorsed by the Roundcube project. The Luminare name and logo are not licensed
          (NOTICE). Sora: SIL Open Font License 1.1. Includes React and React DOM (MIT).
        </p>
      </footer>
    </>
  );
}
