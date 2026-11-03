import { computed, ref } from 'vue'
import { API } from '@/api/methods'
import { useProduct } from '@/composables/useProduct'
import { useTrialOnboarding } from '@/composables/useTrialOnboarding'
import {
	frappeErrorMessage,
	getFrappe,
	methodUrl,
	postFrappe,
} from '@/lib/auth'
import type {
	Onboarding,
	OnboardingProfile,
	SeatQuote,
} from '@/types/onboarding'

export type ProfileAnswers = Pick<
	OnboardingProfile,
	| 'full_name'
	| 'mobile'
	| 'country'
	| 'organisation'
	| 'business_type'
	| 'headcount_bracket'
	| 'turnover_band'
	| 'seats'
>

export type BillingDetails = Pick<
	OnboardingProfile,
	'address_line1' | 'city' | 'country' | 'tax_id'
>

// One read shared by both steps, so step 2 opens on the answers step 1 just saved.
const onboarding = ref<Onboarding | null>(null)

/** The onboarding steps 1 and 2 of an invited owner: the team, its answers and its prices. */
export function useSetupOnboarding() {
	const { productKey } = useProduct()
	const { team, prepareTeam } = useTrialOnboarding()
	const loading = ref(false)
	const loadError = ref('')

	const pricing = computed(() => onboarding.value?.pricing ?? null)

	async function load(): Promise<void> {
		loading.value = true
		loadError.value = ''
		try {
			await prepareTeam()
			onboarding.value = await getFrappe<Onboarding>(
				methodUrl(API.getOnboarding),
				{ team: team.value, product: productKey.value || undefined },
			)
		} catch (exception) {
			loadError.value = frappeErrorMessage(
				exception,
				'Could not open your setup.',
			)
		} finally {
			loading.value = false
		}
	}

	function quoteFor(seats: number): SeatQuote | null {
		return pricing.value?.quotes.find((quote) => quote.seats === seats) ?? null
	}

	async function saveProfile(answers: ProfileAnswers): Promise<void> {
		const profile = await postFrappe<OnboardingProfile>(
			methodUrl(API.saveOnboardingProfile),
			{ ...answers, team: team.value },
		)
		if (onboarding.value) onboarding.value.profile = profile
	}

	async function saveBillingDetails(details: BillingDetails): Promise<void> {
		await postFrappe(methodUrl(API.saveBillingProfile), {
			...details,
			team: team.value,
		})
		if (onboarding.value)
			onboarding.value.profile = { ...onboarding.value.profile, ...details }
	}

	async function startSite(): Promise<void> {
		await postFrappe(methodUrl(API.startOnboardingSite), {
			team: team.value,
			product: onboarding.value?.product?.name ?? undefined,
		})
	}

	return {
		team,
		onboarding,
		pricing,
		loading,
		loadError,
		load,
		quoteFor,
		saveProfile,
		saveBillingDetails,
		startSite,
	}
}
