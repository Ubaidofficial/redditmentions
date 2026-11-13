// Used by astro.config.mjs (runs in plain Node, so it reads the JSON from disk).
import { readFileSync } from 'node:fs';
import { makeIsLaunchPath } from './launch-core.mjs';

export const isLaunchPath = makeIsLaunchPath(JSON.parse(readFileSync(new URL('./launch-pages.json', import.meta.url), 'utf8')));
