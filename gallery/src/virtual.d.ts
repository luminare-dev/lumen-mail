// The data the gallery's Vite plugin reads from this repository at build time (gallery/data.mjs).
declare module "virtual:lumen-gallery" {
  export interface Pair {
    fg: string;
    bg: string;
    min: number;
    use: string;
    where: string;
  }
  export interface Tokens {
    brand: Record<string, string>;
    light: Record<string, string>;
    dark: Record<string, string>;
    roles: string[];
    shape: Record<string, string>;
  }
  export interface SkinInfo {
    lumenVersion: string | null;
    roundcubeVersion: string | null;
    builtAt: string | null;
    bootstrap: boolean;
  }
  const data: {
    version: string;
    tokens: Tokens;
    pairs: Pair[];
    labels: { en: Record<string, string>; de: Record<string, string> };
    skin: SkinInfo | null;
  };
  export default data;
}
