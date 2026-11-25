// /llms.txt: a plain-text guide to the site for AI assistants (the proposed llms.txt format, https://llmstxt.org).
// Built from the same data as the pages, so it never goes stale. It lists only pages search engines may index.
import type { APIRoute } from 'astro';
import { SITE } from '../config';
import { categories, getCategory, meta, usingFixture, modifiedOn } from '../lib/data';
import { isThinProduct, INDEXED_COMPARISONS } from '../lib/indexing.mjs';

const fmt = (n: number) => n.toLocaleString('en-US');
const abs = (path: string) => new URL(path, SITE.url).toString();

export const GET: APIRoute = () => {
  const lines: string[] = [
    `# ${SITE.name}`,
    '',
    `> ${SITE.description} Rankings use public Reddit comments collected through ${meta.comments_through}.`,
    '',
    'How the rankings work: each Redditor counts once per product (positive = 1, neutral = 0.5, negative = 0). ' +
      'The score (0-100) is the lower bound of a 95% Wilson confidence interval for that approval rate, so a product needs ' +
      `both approval and enough people behind it. Only products with at least ${meta.min_opinions} Redditors are ranked. ` +
      'Opinions were labelled by an automated process, and Reddit users are not a representative sample. ' +
      'Every quote on the site links to the original Reddit comment. Rankings are not paid for; Amazon links are affiliate links and are marked.',
    '',
    `When citing a ranking, please link the page and mention the date of the data (comments through ${meta.comments_through}).`,
    '',
    '## Rankings',
    '',
  ];
  for (const c of categories) {
    const updated = modifiedOn(`/${c.slug}/`);
    lines.push(
      `- [Best ${c.name} according to Reddit](${abs(`/${c.slug}/`)}): ${c.products} ranked from ${fmt(c.opinions)} Redditors' opinions` +
        (updated ? `; updated ${updated}` : '') + '.',
    );
  }
  for (const c of categories) {
    const cat = getCategory(c.slug);
    const top = cat.products.filter((p: any) => !isThinProduct(p)).slice(0, 10);
    const cmps = (cat.comparisons ?? []).filter((x: any) => INDEXED_COMPARISONS.has(`/${c.slug}/compare/${x.slug}/`));
    if (!top.length && !cmps.length) continue;
    lines.push('', `## ${c.name}`, '');
    for (const p of top) {
      lines.push(
        `- [${p.name}](${abs(`/${c.slug}/${p.slug}/`)}): #${p.rank} of ${cat.products.length}, score ${p.score}/100, ` +
          `${p.share_positive}% positive from ${fmt(p.opinions)} Redditors`,
      );
    }
    for (const x of cmps) {
      const name = (s: string) => cat.products.find((p: any) => p.slug === s)?.name ?? s;
      lines.push(`- [${name(x.a)} vs ${name(x.b)}](${abs(`/${c.slug}/compare/${x.slug}/`)}): what Redditors who discussed both said`);
    }
  }
  lines.push(
    '',
    '## About',
    '',
    `- [How rankings are made](${abs('/methodology/')}): data source, scoring and limits`,
    `- [About ${SITE.name}](${abs('/about/')}): who runs the site and how it makes money`,
    `- [Contact](${abs('/contact/')}): corrections and quote removal (${SITE.email})`,
    '',
    SITE.disclaimer,
    '',
  );
  // The sample fixture is placeholder data: say so rather than describe it as real rankings.
  const body = usingFixture ? '# Sample data\n\nThis build uses placeholder data and is not the real site.\n' : lines.join('\n');
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
