import type { APIRoute } from 'astro';
import { getCategory } from '../lib/data';
import { launchedCategories } from '../lib/launch';
import { categoryMarkdown } from '../lib/markdown';

// One Markdown file per released category page, at the page's address + ".md" (e.g. /best-robot-vacuums-reddit.md).
export function getStaticPaths() {
  return launchedCategories().map((c: any) => ({ params: { category: c.slug } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(categoryMarkdown(getCategory(params.category as string)), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
