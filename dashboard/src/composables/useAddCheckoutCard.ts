// Add a card on the Checkout.com rail (Flow). Counterpart to useAddStripeCard.
//
// 1. initiate_card_setup opens a Flow payment session for amount 0 (a card
//    verification that stores the card) and a pending Payment Method.
// 2. Flow collects the card, runs 3DS and reports the payment complete.
// 3. confirm_card: the backend reads the payment back from Checkout.com by the
//    session reference, stores the card and activates it. The browser sends only
//    the Payment Method name.

import { useCall } from 'frappe-ui'
import { ref } from 'vue'
import { API, method } from '@/api/methods'
import { type MountedFlow, mountCheckoutFlow } from '@/lib/checkout'
import { getErrorMessage, successToast } from '@/lib/feedback'
import type { CheckoutOrder } from '@/lib/gateway'

interface ConfirmCardResult {
	payment_method: string
	status: string
	message?: string
}

// Checkout.com can list a payment by its reference a moment after Flow reports it.
const CONFIRM_TRIES = 4
const CONFIRM_WAIT_MS = 1500

export function useAddCheckoutCard({
	onDone,
}: {
	onDone?: (res: ConfirmCardResult) => void
} = {}) {
	const initiate = useCall<CheckoutOrder, { team: string }>({
		url: method(API.initiateCardSetup),
		method: 'POST',
		immediate: false,
	})
	const confirm = useCall<ConfirmCardResult, { payment_method?: string }>({
		url: method(API.confirmCard),
		method: 'POST',
		immediate: false,
	})
	const ready = ref(false)
	const submitting = ref(false)
	const error = ref('')
	let flow: MountedFlow | null = null

	async function mount(
		el: HTMLElement,
		{ team }: { team: string },
	): Promise<void> {
		error.value = ''
		await initiate.submit({ team })
		const order = initiate.data
		if (initiate.error || !order?.payment_method)
			throw (
				initiate.error ??
				new Error('Could not start card setup. Please try again.')
			)
		flow = await mountCheckoutFlow(el, order, {
			onReady: () => {
				ready.value = true
			},
			onCompleted: () => void finish(order.payment_method as string),
			onError: (e) => {
				error.value = getErrorMessage(
					e,
					'The card could not be checked. Try again or use another card.',
				)
			},
		})
	}

	async function finish(
		paymentMethod: string,
	): Promise<ConfirmCardResult | undefined> {
		submitting.value = true
		error.value = ''
		try {
			for (let attempt = 1; attempt <= CONFIRM_TRIES; attempt++) {
				await confirm.submit({ payment_method: paymentMethod })
				if (!confirm.error) break
				if (attempt === CONFIRM_TRIES) throw confirm.error
				await new Promise((resolve) => setTimeout(resolve, CONFIRM_WAIT_MS))
			}
			const res = confirm.data
			if (!res || res.status !== 'Active') {
				error.value =
					res?.message ?? "Couldn't verify that card. Try a different one"
				return
			}
			successToast('Card added')
			onDone?.(res)
			return res
		} catch (e) {
			error.value = getErrorMessage(e, 'Could not add card')
		} finally {
			submitting.value = false
		}
	}

	function destroy(): void {
		flow?.destroy()
		flow = null
		ready.value = false
		error.value = ''
	}

	return { mount, destroy, ready, submitting, error }
}
