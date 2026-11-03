/** The four onboarding steps of an invited owner, in the header stepper. */
export interface SetupStep {
	label: string
	/** The console route of the step. Null until the step is built. */
	path: string | null
}

export const SETUP_STEPS: SetupStep[] = [
	{ label: 'Organization Setup', path: '/onboarding/profile' },
	{ label: 'Billing & Trial', path: '/onboarding/billing' },
	{ label: 'Team', path: '/onboarding/team' },
	{ label: 'Master Setup', path: null },
]
