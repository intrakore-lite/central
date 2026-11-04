// The apps of a plan as onboarding reads them out. Central sends them in bundle order (the
// product's own apps first, dependencies and the AI assistant last), so nothing here sorts.

/** How many apps a short list names before "and N more modules". */
export const NAMED_MODULES = 3

/** "CRM, Estimation & Procurement modules": a short list reads better than a comma chain. */
export function listModules(names: string[]): string {
	const shown = names.slice(0, NAMED_MODULES)
	const rest = names.length - shown.length
	if (rest > 0) return `${shown.join(', ')} and ${rest} more modules`
	if (shown.length === 1) return `the ${shown[0]} module`
	return `${shown.slice(0, -1).join(', ')} & ${shown[shown.length - 1]} modules`
}
