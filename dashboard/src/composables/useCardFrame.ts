import { computed, nextTick, onScopeDispose, type Ref, ref } from 'vue'
import { API } from '@/api/methods'
import { useAddStripeCard } from '@/composables/useAddStripeCard'
import {
	frappeErrorMessage,
	getFrappe,
	methodUrl,
	postFrappe,
} from '@/lib/auth'
import type { CardSetupHandles } from '@/types/onboarding'

/** How the gateway takes the card. */
export type CardFrameMode =
	| 'idle'
	| 'loading'
	| 'stripe'
	| 'iframe'
	| 'redirect'
	| 'returned'
	| 'unavailable'
	| 'error'

interface PaymentMethodOptions {
	adapter_key: string | null
	publishable_key: string | null
	currency: string
}

interface ConfirmedCard {
	payment_method: string
	status: string
	message?: string
}

// A card page the browser left for comes back to this page. The pending method survives the trip here.
const PENDING_KEY = 'central:onboarding-card-setup'
// The hosted card page of a framed gateway posts this when the card is saved.
const SAVED_MESSAGE = 'central:card-saved'

/**
 * The card step of onboarding, on whatever the team's card gateway hands back.
 *
 * 1. Stripe answers with a client secret: the card goes in a Stripe Element.
 * 2. A framed gateway, such as Telr, answers with `iframe_url`: its own page is framed here.
 * 3. A redirect gateway answers with `redirect_url`: the browser leaves and comes back.
 *
 * In every case Central confirms the card from the gateway, never from the browser.
 */
export function useCardFrame(team: Ref<string>) {
	const mode = ref<CardFrameMode>('idle')
	const handles = ref<CardSetupHandles | null>(null)
	const error = ref('')
	const isConfirming = ref(false)
	const isSavedInFrame = ref(false)
	const stripeCard = useAddStripeCard()

	const isReady = computed(
		() =>
			(mode.value === 'stripe' && stripeCard.complete.value) ||
			mode.value === 'iframe' ||
			mode.value === 'returned',
	)

	async function start(stripeElement: () => HTMLElement | null): Promise<void> {
		mode.value = 'loading'
		error.value = ''
		if (readPending()) {
			mode.value = 'returned'
			return
		}
		try {
			const options = await getFrappe<PaymentMethodOptions>(
				methodUrl(API.paymentMethodOptions),
				{ team: team.value },
			)
			if (options.adapter_key === 'Stripe' && options.publishable_key)
				return await startStripe(options.publishable_key, stripeElement)
			await startHostedPage()
		} catch (exception) {
			mode.value = 'error'
			error.value = frappeErrorMessage(
				exception,
				'Could not open the card form. Try again.',
			)
		}
	}

	async function startStripe(
		publishableKey: string,
		stripeElement: () => HTMLElement | null,
	): Promise<void> {
		mode.value = 'stripe'
		// The element is in the page only once the mode renders it.
		await nextTick()
		const element = stripeElement()
		if (!element) throw new Error('The card form could not load.')
		await stripeCard.mount(element, { team: team.value, publishableKey })
	}

	async function startHostedPage(): Promise<void> {
		handles.value = await postFrappe<CardSetupHandles>(
			methodUrl(API.initiateCardSetup),
			{ team: team.value },
		)
		if (handles.value.iframe_url) mode.value = 'iframe'
		else if (handles.value.redirect_url) mode.value = 'redirect'
		else mode.value = 'unavailable'
	}

	function leaveForHostedPage(): void {
		const { redirect_url, payment_method } = handles.value ?? {}
		if (!redirect_url || !payment_method) return
		sessionStorage.setItem(
			PENDING_KEY,
			JSON.stringify({ team: team.value, payment_method }),
		)
		window.location.assign(redirect_url)
	}

	/** Activate the saved card. Returns why it failed, or an empty string. */
	async function confirm(): Promise<string> {
		isConfirming.value = true
		error.value = ''
		try {
			if (mode.value === 'stripe') {
				const result = await stripeCard.submit()
				return result ? '' : stripeCard.error.value || 'Could not add the card.'
			}
			const paymentMethod =
				readPending() ?? handles.value?.payment_method ?? null
			if (!paymentMethod) return 'Open the card form first.'
			const result = await postFrappe<ConfirmedCard>(
				methodUrl(API.confirmCard),
				{ payment_method: paymentMethod },
			)
			if (result.status !== 'Active')
				return (
					result.message || 'We could not verify this card. Try another one.'
				)
			sessionStorage.removeItem(PENDING_KEY)
			return ''
		} catch (exception) {
			return frappeErrorMessage(
				exception,
				'Finish entering the card in the secure form, then try again.',
			)
		} finally {
			isConfirming.value = false
		}
	}

	function readPending(): string | null {
		try {
			const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null')
			return pending?.team === team.value ? pending.payment_method : null
		} catch {
			return null
		}
	}

	// Only the framed page's own origin may say that the card is saved.
	function onMessage(event: MessageEvent): void {
		const frameUrl = handles.value?.iframe_url
		if (!frameUrl || event.origin !== new URL(frameUrl).origin) return
		if (event.data?.type === SAVED_MESSAGE) isSavedInFrame.value = true
	}

	window.addEventListener('message', onMessage)
	onScopeDispose(() => {
		window.removeEventListener('message', onMessage)
		stripeCard.destroy()
	})

	return {
		mode,
		handles,
		error,
		stripeError: stripeCard.error,
		isReady,
		isConfirming,
		isSavedInFrame,
		start,
		leaveForHostedPage,
		confirm,
	}
}
