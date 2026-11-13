// The words on a category page, computed once from its data and shared by the HTML page, the Markdown file and llms.txt,
// so they can never disagree.
import { meta } from './data';
import { AMAZON_TAG } from '../config';
import { YEAR, lower, clamp, withBrand, firstThatFits, joinList, topBrands, themes } from './seo';

export const fmt = (n: number) => n.toLocaleString('en-US');

export function categoryCopy(cat: any) {
  const products: any[] = cat.products;
  const unit: string = cat.unit ?? 'Redditors';
  const commentLevel = cat.source === 'redrecs';
  const x = lower(cat.name); // "robot vacuums"
  const n = products.length;
  const unitL = unit === 'comments' ? 'Reddit comments' : 'Redditors';
  const voices = products.reduce((s, p) => s + p.opinions, 0);
  const top = products[0];
  const second = products[1];
  const third = products[2];
  const mostDiscussed = [...products].sort((a, b) => b.opinions - a.opinions)[0];
  const crowd = products
    .filter((p) => p.opinions >= 100 && p.slug !== top.slug && p.slug !== mostDiscussed.slug)
    .sort((a, b) => b.share_positive - a.share_positive || b.opinions - a.opinions)[0];
  const leaders = topBrands(products, 3);
  const praised = themes(products, 'likes', 5);
  const criticised = themes(products, 'dislikes', 5);
  const minVoices = commentLevel ? meta.rr_min : meta.min_opinions;
  const kind = commentLevel ? 'Reddit Comments' : 'Redditors';
  const title = firstThatFits(
    [
      withBrand(`Best ${cat.name} Reddit ${YEAR}: Top ${n} Ranked by ${kind}`, 64),
      `Best ${cat.name} Reddit ${YEAR}: Top ${n} Ranked by ${kind}`,
      `Best ${cat.name} Reddit ${YEAR}: Top ${n} Ranked`,
      `Best ${cat.name} Reddit ${YEAR}`,
    ],
    66,
  );
  const description = clamp(
    `Best ${x} Reddit recommends in ${YEAR}: ${n} ranked using ${fmt(voices)} ${unitL}. See what Redditors praise, what they warn about, and the original comments.`,
  );
  const lead =
    `Looking for the best ${x} on Reddit? We ranked ${n} ${x} using ${fmt(voices)} ${unitL}. ` +
    `${top.name} leads with a score of ${top.score}/100 (${top.share_positive}% positive), ahead of ${second.name} and ${third.name}. ` +
    `Every product below has at least ${minVoices} ${unitL} behind it, so a few enthusiasts cannot carry a product to the top.`;
  const saysLead =
    (leaders.length > 0 ? `${joinList(leaders)} ${leaders.length > 1 ? 'show' : 'shows'} up most often in the top ten best ${x} on Reddit. ` : '') +
    `${mostDiscussed.name} is the most discussed, with ${fmt(mostDiscussed.opinions)} ${unitL}, while ${top.name} earns the best confidence-weighted score.` +
    (praised.length > 0 ? ' Here is what comes up again and again in the comments.' : '');
  const method = commentLevel
    ? `We count positive, neutral and negative Reddit comments about each product, then score it with the lower bound of a 95% confidence interval on its approval rate. A product liked by 90% of 20 comments ranks below one liked by 85% of 300. Only products with at least ${minVoices} comments are ranked.`
    : `We collect public Reddit comments about each product, count each Redditor once per product, and score it with the lower bound of a 95% confidence interval on its approval rate. A product liked by 90% of 20 people ranks below one liked by 85% of 300. Only products with at least ${minVoices} Redditors are ranked.`;
  const faq = [
    {
      q: `What are the best ${x} on Reddit?`,
      a: `${top.name} is the top-ranked of ${n} ${x} in our Reddit-based ranking, with a score of ${top.score}/100 and ${top.share_positive}% positive opinions from ${fmt(top.opinions)} ${unitL}. ${second.name} and ${third.name} follow.`,
    },
    {
      q: `Which ${x} do Redditors talk about most?`,
      a: `${mostDiscussed.name} has the most discussion in our data, with ${fmt(mostDiscussed.opinions)} ${unitL}.` + (crowd ? ` Among well-discussed picks, Redditors favour ${crowd.name}, with ${crowd.share_positive}% positive opinions.` : ''),
    },
    ...(criticised.length
      ? [{ q: `What do Redditors complain about with ${x}?`, a: `The most common complaints are ${joinList(criticised.slice(0, 3).map((c) => c.title.toLowerCase()))}. Each product page lists what Reddit praises and criticises about it.` }]
      : []),
    { q: `How are the best ${x} on Reddit ranked?`, a: method },
    {
      q: `Does AskTheSubs earn money from these ${x} links?`,
      a: AMAZON_TAG
        ? 'Some links to Amazon are affiliate links, so we may earn a commission if you buy, at no extra cost to you. Rankings are calculated from Reddit opinions only, and commissions do not influence them.'
        : 'Buy buttons currently link to Amazon without an affiliate tag. If that changes we will say so. Rankings come from Reddit opinions only.',
    },
  ];
  return { products, unit, unitL, commentLevel, x, n, voices, top, second, third, mostDiscussed, crowd, leaders, praised, criticised, minVoices, title, description, lead, saysLead, method, faq };
}
