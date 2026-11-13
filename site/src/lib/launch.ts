// Used by the page layout (bundled by Vite, so the JSON is imported). Same rules as astro.config.mjs via launch-core.mjs,
// so the sitemap and the robots meta tags can never disagree.
import cfg from '../../launch-pages.json';
import { makeIsLaunchPath } from '../../launch-core.mjs';

export const isLaunchPath: (pathname: string) => boolean = makeIsLaunchPath(cfg as any);
