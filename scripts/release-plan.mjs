#!/usr/bin/env node
// Prints the release plan: which pages go live today and over the next days.
//   node scripts/release-plan.mjs            # today + the next 14 days
//   node scripts/release-plan.mjs 30         # next 30 days
//   PUBLIC_RELEASE_DATE=2026-12-01 node scripts/release-plan.mjs
import { readFileSync } from 'node:fs';
import { planReleases, releaseDate, releasedQueueCount } from '../site/launch-core.mjs';

const cfg = JSON.parse(readFileSync(new URL('../site/launch-pages.json', import.meta.url), 'utf8'));
const days = Number(process.argv[2]) || 14;
const from = releaseDate(process.env.PUBLIC_RELEASE_DATE);
const plan = planReleases(cfg, from, days);
console.log(`Start date ${cfg.schedule.startDate}; ${cfg.paths.length + cfg.categories.length} pages live on day 0; ${cfg.queue.length} queued; ${cfg.schedule.perDayMin}-${cfg.schedule.perDayMax} released per day.\n`);
for (const d of plan) {
  console.log(`${d.date}  live: ${String(d.liveTotal).padStart(3)}  new: ${d.newToday.length ? d.newToday.join(', ') : '-'}`);
}
const left = cfg.queue.length - releasedQueueCount(cfg, new Date(Date.parse(plan[plan.length - 1].date + 'T12:00:00Z')));
console.log(`\n${left} queued page(s) still unreleased after ${plan[plan.length - 1].date}.`);
