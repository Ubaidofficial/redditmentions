// Used by pages (bundled by Vite, so the JSON is imported). Same rules as astro.config.mjs via launch-core.mjs, so the
// sitemap, the robots meta tags, the markdown files and llms.txt can never disagree.
import cfg from '../../launch-pages.json';
import { makeIsLaunchPath, releaseDate } from '../../launch-core.mjs';
import { INDEX_ALL } from '../config';
import { categories } from './data';

const isLaunch: (pathname: string) => boolean = makeIsLaunchPath(cfg as any, releaseDate(import.meta.env.PUBLIC_RELEASE_DATE));

/** Is this page released (submitted for indexing)? Everything is when PUBLIC_INDEX_PAGES=all. */
export const isLaunchPath = (pathname: string) => INDEX_ALL || isLaunch(pathname);

/** The category pages released today, in site order. */
export const launchedCategories = () => categories.filter((c: any) => isLaunchPath(`/${c.slug}/`));
