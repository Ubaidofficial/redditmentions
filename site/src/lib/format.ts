export const fmt = (n: number) => n.toLocaleString('en-US');

// How much evidence stands behind a product, from the number of Redditors counted.
export function evidence(n: number) {
  if (n >= 300) return { dots: 4, label: 'Strong evidence' };
  if (n >= 100) return { dots: 3, label: 'Solid evidence' };
  if (n >= 50) return { dots: 2, label: 'Moderate evidence' };
  return { dots: 1, label: 'Early evidence' };
}

// Share of the category's ranked products this one outscores.
export function outscores(products: any[], score: number) {
  if (products.length < 2) return 0;
  return Math.round((100 * products.filter((p) => p.score < score).length) / (products.length - 1));
}

export function median(values: number[]) {
  const a = [...values].sort((x, y) => x - y);
  const m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : Math.round((a[m - 1] + a[m]) / 2);
}
