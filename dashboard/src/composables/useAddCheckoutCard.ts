// Add a card on the Checkout.com rail in the console card dialog. Counterpart to
// useAddStripeCard; the Flow form itself is useCheckoutFlow, shared with onboarding.
//
// 1. initiate_card_setup opens a Flow payment session for amount 0 (a card
//    verification that stores the card) and a pending Payment Method.
// 2. Flow collects the card. Its own "Pay" button is hidden: the dialog's "Save card"
//    button calls save(), Flow runs 3DS and reports the payment complete.
// 3. confirm_card: the backend reads the payment back from Checkout.com, stores the
//    card and activates it. The browser sends the Payment Method name and Flow's
//    payment id, which Central uses only if it carries the session's reference.

import { useCall } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { API, method } from '@/api/methods'
import { useCheckoutFlow } from '@/composables/useCheckoutFlow'
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
	const confirm = useCall<
		ConfirmCardResult,
		{ payment_method?: string; payment_id?: string }
	>({
		url: method(API.confirmCard),
		method: 'POST',
		immediate: false,
	})
	const flow = useCheckoutFlow()
	const submitting = ref(false)
	const error = ref('')
	let paymentMethod = ''

	async function mount(
		el: HTMLElement,
		{ team }: { team: string },
	): Promise<void> {
		error.value = ''
		await initiate.submit({ team })
		const order = initiate.data
		if (initiate.error || !order?.payment_method || !order.checkout)
			throw (
				initiate.error ??
				new Error('Could not start card setup. Please try again.')
			)
		paymentMethod = order.payment_method
		await flow.mount(el, order.checkout)
	}

	watch(flow.completed, (completed) => {
		if (completed && paymentMethod) void finish()
	})

	async function finish(): Promise<ConfirmCardResult | undefined> {
		submitting.value = true
		error.value = ''
		try {
			for (let attempt = 1; attempt <= CONFIRM_TRIES; attempt++) {
				await confirm.submit({
					payment_method: paymentMethod,
					payment_id: flow.paymentId.value || undefined,
				})
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
		flow.destroy()
		flow.completed.value = false
		flow.paymentId.value = ''
		paymentMethod = ''
		error.value = ''
	}

	return {
		mount,
		save: flow.submit,
		destroy,
		/** Flow is sending the card (before Central confirms it). */
		saving: flow.isSubmitting,
		submitting,
		error: computed(() => error.value || flow.error.value),
	}
}
