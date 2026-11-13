// Used by astro.config.mjs (plain Node, so it reads the JSON from disk).
import { readFileSync } from 'node:fs';
import { makeIsLaunchPath, releaseDate } from './launch-core.mjs';

export const launchConfig = JSON.parse(readFileSync(new URL('./launch-pages.json', import.meta.url), 'utf8'));
export const makeConfigIsLaunchPath = (envDate) => makeIsLaunchPath(launchConfig, releaseDate(envDate));
