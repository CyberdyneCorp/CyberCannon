/**
 * Telling a placement from a navigation, which is the one thing they share.
 *
 * `viewer-3d` asks for orbit, pan and zoom *"using pointer input"* and for an
 * annotation to be placed *"by pointing at"* a part. Those are the same button
 * on the same surface, so something has to decide which one a gesture was — and
 * `model-sheet-2d` already settled the shape of that decision for the 2D sheet:
 * a gesture that moved is navigation, and a gesture that did not is a
 * placement.
 *
 * The threshold is in **pixels of the display**, not in scene units, because
 * what is being measured is a hand: a person trying to tap moves a few pixels,
 * and a person trying to orbit moves dozens. It is here rather than inside a
 * component so it can be checked without one.
 */

export interface Point {
	readonly x: number;
	readonly y: number;
}

/**
 * How far a pointer may travel and still have been a tap.
 *
 * Generous enough for a trackpad and a stylus, small enough that a deliberate
 * orbit never reads as a placement. `model-sheet-2d`'s sheet uses the same
 * reasoning for the same reason.
 */
export const TAP_TOLERANCE_PX = 4;

/** Whether the pointer stayed put between pressing and releasing. */
export function isTap(from: Point | null, to: Point, tolerance = TAP_TOLERANCE_PX): boolean {
	if (from === null) return false;
	return Math.hypot(to.x - from.x, to.y - from.y) <= tolerance;
}

/**
 * Where a pointer is in normalized device coordinates, for a raycast.
 *
 * `-1..1` on both axes with `y` flipped, which is what a projection camera
 * expects — and a conversion that lives in one place, because a viewer that got
 * it wrong would place every pin mirrored and nothing would say so.
 */
export function deviceCoordinates(
	at: Point,
	box: { left: number; top: number; width: number; height: number }
): { x: number; y: number } {
	if (box.width === 0 || box.height === 0) return { x: 0, y: 0 };
	return {
		x: ((at.x - box.left) / box.width) * 2 - 1,
		y: -(((at.y - box.top) / box.height) * 2 - 1)
	};
}
