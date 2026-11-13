import type { APIRoute } from 'astro';
import { homeMarkdown } from '../lib/markdown';

export const GET: APIRoute = () => new Response(homeMarkdown(), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
