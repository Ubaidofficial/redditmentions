import type { APIRoute } from 'astro';
import { methodologyMarkdown } from '../lib/markdown';

export const GET: APIRoute = () => new Response(methodologyMarkdown(), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
