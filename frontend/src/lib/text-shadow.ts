// Layered drop-shadow that "extrudes" a display headline off its background
// -- many offset shadows of one color, one pixel further out each layer.
// Used across every page that reuses the reference hero's block-letter
// treatment, so the technique (and its tuning) lives in one place.
export function stackedShadow(layers: number, color: string): string {
  return Array.from({ length: layers }, (_, i) => `${i + 1}px ${i + 1}px 0 ${color}`).join(", ");
}
