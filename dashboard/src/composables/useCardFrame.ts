import { computed, nextTick, onScopeDispose, type Ref, ref, watch } from 'vue'
import { API } from '@/api/methods'
import { useAddStripeCard } from '@/composables/useAddStripeCard'
import { useCheckoutFlow } from '@/composables/useCheckoutFlow'
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
	| 'checkout'
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
export const PENDING_KEY = 'central:onboarding-card-setup'
// A hosted card page returns the browser here: inside the frame it posts SAVED_MESSAGE
// to this page; after a redirect it opens the billing step again.
export const CARD_SAVED_PATH = '/dashboard/onboarding/card-saved'
export const SAVED_MESSAGE = 'central:card-saved'

/**
 * The card step of onboarding, on whatever the team's card gateway hands back.
 *
 * 1. Stripe answers with a client secret: the card goes in a Stripe Element.
 * 2. Checkout.com answers with `checkout` handles: the card goes in Checkout Flow.
 * 3. A framed gateway answers with `iframe_url`: its own page is framed here.
 * 4. A redirect gateway answers with `redirect_url`: the browser leaves and comes back.
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
	const checkoutFlow = useCheckoutFlow()

	const isReady = computed(
		() =>
			(mode.value === 'stripe' && stripeCard.complete.value) ||
			(mode.value === 'checkout' && checkoutFlow.completed.value) ||
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
			await startHostedPage(stripeElement)
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

	// The card slot holds the Stripe element or Checkout Flow, whichever the gateway uses.
	async function startHostedPage(
		cardSlot: () => HTMLElement | null,
	): Promise<void> {
		handles.value = await postFrappe<CardSetupHandles>(
			methodUrl(API.initiateCardSetup),
			{
				team: team.value,
				return_url: `${window.location.origin}${CARD_SAVED_PATH}`,
			},
		)
		if (handles.value.checkout) {
			// A 3-D Secure check can send the browser to the return page and back to this step.
			// Remember the card, so the step confirms it instead of opening a new form.
			if (handles.value.payment_method)
				savePending(handles.value.payment_method)
			mode.value = 'checkout'
			await nextTick()
			const element = cardSlot()
			if (!element) throw new Error('The card form could not load.')
			await checkoutFlow.mount(element, handles.value.checkout)
		} else if (handles.value.iframe_url) mode.value = 'iframe'
		else if (handles.value.redirect_url) mode.value = 'redirect'
		else mode.value = 'unavailable'
	}

	function savePending(paymentMethod: string): void {
		sessionStorage.setItem(
			PENDING_KEY,
			JSON.stringify({ team: team.value, payment_method: paymentMethod }),
		)
	}

	function leaveForHostedPage(): void {
		const { redirect_url, payment_method } = handles.value ?? {}
		if (!redirect_url || !payment_method) return
		savePending(payment_method)
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
				{
					payment_method: paymentMethod,
					payment_id:
						checkoutFlow.paymentId.value || readPendingPaymentId() || undefined,
				},
			)
			if (result.status !== 'Active') {
				forgetReturnedCard()
				return (
					result.message || 'We could not verify this card. Try another one.'
				)
			}
			sessionStorage.removeItem(PENDING_KEY)
			return ''
		} catch (exception) {
			forgetReturnedCard()
			return frappeErrorMessage(
				exception,
				'Finish entering the card in the secure form, then try again.',
			)
		} finally {
			isConfirming.value = false
		}
	}

	// A returned card that cannot be confirmed is dropped, so the next try opens a new form.
	function forgetReturnedCard(): void {
		if (mode.value !== 'returned') return
		sessionStorage.removeItem(PENDING_KEY)
		mode.value = 'idle'
	}

	function readPendingPaymentId(): string | null {
		try {
			const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null')
			return pending?.team === team.value ? (pending.payment_id ?? null) : null
		} catch {
			return null
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

	// The return page inside the frame is on this site, so only this origin may say that
	// the card is saved. Central still reads the card from the gateway before trusting it.
	function onMessage(event: MessageEvent): void {
		if (mode.value !== 'iframe' || event.origin !== window.location.origin)
			return
		if (event.data?.type === SAVED_MESSAGE) isSavedInFrame.value = true
	}

	window.addEventListener('message', onMessage)
	onScopeDispose(() => {
		window.removeEventListener('message', onMessage)
		stripeCard.destroy()
		checkoutFlow.destroy()
	})
	// Checkout Flow has its own pay button. Its success confirms the card like a framed page does.
	watch(checkoutFlow.completed, (completed) => {
		if (completed) isSavedInFrame.value = true
	})

	return {
		mode,
		handles,
		error,
		stripeError: computed(
			() => stripeCard.error.value || checkoutFlow.error.value,
		),
		isReady,
		isConfirming,
		isSavedInFrame,
		start,
		leaveForHostedPage,
		confirm,
	}
}
