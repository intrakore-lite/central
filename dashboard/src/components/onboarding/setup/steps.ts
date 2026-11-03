/** The four onboarding steps of an invited owner, in the header stepper. */
export interface SetupStep {
	label: string
	/** The console route of the step. */
	path: string
}

export const SETUP_STEPS: SetupStep[] = [
	{ label: 'Organization Setup', path: '/onboarding/profile' },
	{ label: 'Billing & Trial', path: '/onboarding/billing' },
	{ label: 'Team', path: '/onboarding/team' },
	{ label: 'Master Setup', path: '/onboarding/modules-setup' },
]

/** The console page of onboarding step 5, which means done. */
export const SETUP_DONE_PATH = '/servers'

/** Where an owner at `step` (get_onboarding's progress) belongs. */
export function stepPath(step: number): string {
	return SETUP_STEPS[step - 1]?.path ?? SETUP_DONE_PATH
}

/**
 * Where a page of step `current` sends an owner whose progress is `step`, or
 * null to stay. A finished owner goes to the console. An owner who has not
 * reached `current` goes back to their step. Steps 1 and 2 stay editable until
 * the site starts; after that the owner goes on to their step.
 */
export function resumeRedirect(current: number, step: number): string | null {
	if (step > SETUP_STEPS.length) return SETUP_DONE_PATH
	if (step < current) return stepPath(step)
	if (current <= 2 && step >= 3) return stepPath(step)
	return null
}
