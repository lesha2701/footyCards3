/** Picture symbols of club / «Менеджер» emblems: "img_<key>" is
 * static/emblems/symbols/<key>.webp, a white silhouette tinted by ImageSymbol. */
export function isImageSymbol(symbol: string | null | undefined): symbol is string {
  return !!symbol && symbol.startsWith("img_");
}
