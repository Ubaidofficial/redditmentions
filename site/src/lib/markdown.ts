// Markdown versions of pages, for people and AI tools that prefer plain text. Built from the same data and copy as the HTML pages.
import { SITE } from '../config';
import { meta, getCategory } from './data';
import { categoryCopy, fmt } from './copy';
import { YEAR, abs, sentence } from './seo';
import { launchedCategories } from './launch';

const cell = (s: string) => String(s ?? '').replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim();

export function categoryMarkdown(cat: any): string {
  const c = categoryCopy(cat);
  const url = (p?: any) => abs(p ? `/${cat.slug}/${p.slug}/` : `/${cat.slug}/`);
  const out: string[] = [];
  out.push(`# Best ${cat.name} according to Reddit (${YEAR})`, '', `> ${c.description}`, '');
  out.push(`Page: ${url()}  `, `Data: Reddit comments through ${meta.comments_through}. Independent site, not affiliated with Reddit.`, '');
  if (c.commentLevel) {
    out.push('**Comment-level topic.** Counts come from a third-party analysis of Reddit comments. Repeat commenters are not merged and individual comments are not shown. The order is our own confidence score.', '');
  }
  out.push(c.lead, '');
  out.push(`## Best ${c.x} Reddit recommends: our top picks`, '');
  out.push(`- **Top pick:** [${c.top.name}](${url(c.top)}), score ${c.top.score}/100, ${c.top.share_positive}% positive, ${fmt(c.top.opinions)} ${c.unitL}`);
  if (c.mostDiscussed.slug !== c.top.slug) out.push(`- **Most discussed:** [${c.mostDiscussed.name}](${url(c.mostDiscussed)}), ${fmt(c.mostDiscussed.opinions)} ${c.unitL}, ${c.mostDiscussed.share_positive}% positive`);
  if (c.crowd) out.push(`- **Crowd favourite:** [${c.crowd.name}](${url(c.crowd)}), ${c.crowd.share_positive}% positive with 100+ ${c.unitL}`);
  out.push('', `## All ${c.n} best ${c.x}, ranked by Reddit`, '');
  out.push(`| Rank | Product | Score /100 | Positive | ${c.unitL} | Praised for | Criticised for |`, '|---|---|---|---|---|---|---|');
  for (const p of c.products) {
    out.push(`| ${p.rank} | [${cell(p.name)}](${url(p)}) | ${p.score} | ${p.share_positive}% | ${fmt(p.opinions)} | ${cell(p.likes[0]?.title ?? '')} | ${cell(p.dislikes[0]?.title ?? '')} |`);
  }
  out.push('', `## What Redditors say about ${c.x}`, '', c.saysLead, '');
  if (c.praised.length) out.push(`### What Redditors praise in ${c.x}`, '', ...c.praised.map((t) => `- ${sentence(t.title)} (${fmt(t.count)} mentions)`), '');
  if (c.criticised.length) out.push('### What Redditors complain about', '', ...c.criticised.map((t) => `- ${sentence(t.title)} (${fmt(t.count)} mentions)`), '');
  out.push(`## Best ${c.x} on Reddit: questions answered`, '');
  for (const f of c.faq) out.push(`### ${f.q}`, '', f.a, '');
  const threads = (cat.threads ?? []) as string[];
  if (threads.length) out.push('## Reddit threads behind this ranking', '', ...threads.map((t) => `- ${t}`), '');
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n';
}

export function methodologyMarkdown(): string {
  return [
    `# How ${SITE.name} ranks products`,
    '',
    `Page: ${abs('/methodology/')}`,
    '',
    '## Where the data comes from',
    `Rankings are built from public Reddit comments about each product, collected through ${meta.comments_through}. Opinions were extracted and labelled positive, neutral or negative by an automated process; some labels will be wrong.`,
    '',
    '## How a product is scored',
    `1. Each Redditor counts once per product, using their overall stance.`,
    `2. Only products with at least ${meta.min_opinions} Redditors are ranked.`,
    '3. The score is the lower bound of a 95% confidence interval (Wilson score) for the approval rate, from 0 to 100. A positive opinion counts as 1, neutral as one half, negative as 0. A product liked by 90% of 20 people can rank below one liked by 85% of 300.',
    '',
    '## Comment-level topics',
    'Some topics come from a third-party analysis of Reddit comments. For those we only have counts of positive, neutral and negative comments per product; repeat commenters are not merged and individual comments are not shown. They use the same confidence score and are marked "comment-level". Where a product appears in both kinds of data, the pages show the two results separately.',
    '',
    '## What this cannot tell you',
    '- Reddit users are not a representative sample, and communities for one brand skew toward that brand.',
    '- Some comments may come from people paid or encouraged to promote a product; this is not detected.',
    `- Products released after ${meta.comments_through} are missing, and opinions about older products may be out of date.`,
    '- For safety-critical products (strollers, car seats) check the manufacturer\'s safety information and recalls.',
    '',
    `${SITE.disclaimer}`,
    '',
  ].join('\n');
}

export function homeMarkdown(): string {
  const cats = launchedCategories();
  return [
    `# ${SITE.name}`,
    '',
    `> ${SITE.tagline} ${SITE.description}`,
    '',
    `Page: ${SITE.url}/`,
    '',
    '## Rankings',
    '',
    ...cats.map((c: any) => `- [Best ${c.name} according to Reddit](${abs(`/${c.slug}.md`)}): ${c.products} ranked`),
    '',
    `- [How rankings are made](${abs('/methodology.md')})`,
    '',
  ].join('\n');
}

export function llmsTxt(): string {
  const cats = launchedCategories();
  const lines = [
    `# ${SITE.name}`,
    '',
    `> ${SITE.tagline} Product rankings built from what people say in Reddit communities, scored by approval rate with a confidence adjustment, with a link to the original comment behind every quote. Independent site, not affiliated with Reddit.`,
    '',
    `Every page below is also available as Markdown at the same address ending in .md. Data covers Reddit comments through ${meta.comments_through}. Rankings use Reddit opinions only.`,
    '',
    '## Rankings',
    '',
  ];
  for (const meta_ of cats) {
    const cat = getCategory(meta_.slug);
    const c = categoryCopy(cat);
    lines.push(`- [Best ${cat.name} according to Reddit](${abs(`/${cat.slug}.md`)}): ${c.n} ranked from ${fmt(c.voices)} ${c.unitL}. Top pick: ${c.top.name}.`);
  }
  lines.push('', '## About', '', `- [How rankings are made](${abs('/methodology.md')}): data sources, scoring and limits`, '', '## Optional', '', `- [All pages in one file](${abs('/llms-full.txt')}): the full Markdown of every page listed above`, '');
  return lines.join('\n');
}

export function llmsFullTxt(): string {
  const parts = [homeMarkdown(), methodologyMarkdown(), ...launchedCategories().map((c: any) => categoryMarkdown(getCategory(c.slug)))];
  return parts.join('\n---\n\n');
}
