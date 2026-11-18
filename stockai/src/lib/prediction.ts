/** Shared prediction semantics — mirrors backend services/ml/recipe.py.
 * Keep in sync: NO_EDGE_THRESHOLD, NO_EDGE_CONFIDENCE_CAP, ENTRY_CONFIDENCE_MIN.
 */
export const NO_EDGE_THRESHOLD = 0.4;
export const NO_EDGE_CONFIDENCE_CAP = 55;
export const ENTRY_CONFIDENCE_MIN = 60;

export function hasClearEdge(up: number, neutral: number, down: number): boolean {
  return Math.max(up, neutral, down) >= NO_EDGE_THRESHOLD;
}
