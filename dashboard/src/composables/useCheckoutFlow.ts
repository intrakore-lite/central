import { ref } from 'vue'
import type { CheckoutSetup } from '@/types/onboarding'

// Checkout Flow, Checkout.com's in-page card component. See
// https://www.checkout.com/docs/payments/accept-payments/accept-a-payment-on-your-website
const FLOW_SCRIPT = 'https://checkout-web-components.checkout.com/index.js'

interface FlowComponent {
	mount(element: HTMLElement): void
	unmount?(): void
	/** Sends the card, for a page that draws its own button. */
	submit(): FlowComponent
	/** True once the customer has entered every detail Flow needs. */
	isValid(): boolean
}

interface FlowOptions {
	/** False hides Flow's own pay button; the page calls submit() instead. */
	showPayButton?: boolean
	onReady?: (component: FlowComponent) => void
	onChange?: (component: FlowComponent) => void
}

interface CheckoutWebComponents {
	create(name: 'flow', options?: FlowOptions): FlowComponent
}

type CheckoutWebComponentsLoader = (options: {
	publicKey: string
	environment: string
	locale: string
	paymentSession: CheckoutSetup['payment_session']
	componentOptions?: { flow?: FlowOptions }
	onPaymentCompleted: (component: unknown, payment: { id: string }) => void
	onError: (component: unknown, error: { message?: string }) => void
}) => Promise<CheckoutWebComponents>

declare global {
	interface Window {
		CheckoutWebComponents?: CheckoutWebComponentsLoader
	}
}

let scriptPromise: Promise<CheckoutWebComponentsLoader> | null = null

function loadFlowScript(): Promise<CheckoutWebComponentsLoader> {
	scriptPromise ??= new Promise((resolve, reject) => {
		const script = document.createElement('script')
		script.src = FLOW_SCRIPT
		script.async = true
		script.onload = () =>
			window.CheckoutWebComponents
				? resolve(window.CheckoutWebComponents)
				: reject(new Error('The Checkout.com card form could not load.'))
		script.onerror = () => {
			scriptPromise = null
			reject(new Error('The Checkout.com card form could not load.'))
		}
		document.head.appendChild(script)
	})
	return scriptPromise
}

/**
 * Checkout Flow in the card slot. `completed` turns true once Checkout has saved the card.
 *
 * The session is a 0 AED card verification, so Flow's own "Pay" button is hidden.
 * The page draws a "Save card" button that calls `submit()`; `canSubmit` enables it.
 */
export function useCheckoutFlow() {
	const completed = ref(false)
	const paymentId = ref('')
	const error = ref('')
	const isValid = ref(false)
	const isSubmitting = ref(false)
	let flow: FlowComponent | null = null

	async function mount(element: HTMLElement, setup: CheckoutSetup) {
		const load = await loadFlowScript()
		const checkout = await load({
			publicKey: setup.public_key,
			environment: setup.environment,
			locale: 'en',
			paymentSession: setup.payment_session,
			componentOptions: { flow: { showPayButton: false } },
			onPaymentCompleted: (_component, payment) => {
				paymentId.value = payment.id
				isSubmitting.value = false
				completed.value = true
			},
			onError: (_component, failure) => {
				isSubmitting.value = false
				error.value =
					failure.message || 'Checkout.com could not save this card.'
			},
		})
		flow = checkout.create('flow', {
			showPayButton: false,
			onChange: (component) => {
				isValid.value = component.isValid()
				if (isValid.value) error.value = ''
			},
		})
		flow.mount(element)
	}

	/** Save the card: Flow runs the 0 AED verification and any 3-D Secure check. */
	function submit() {
		if (!flow || isSubmitting.value || completed.value) return
		if (!flow.isValid()) {
			// Flow marks the missing fields on a submit it cannot send.
			error.value = 'Enter all the card details first.'
			flow.submit()
			return
		}
		error.value = ''
		isSubmitting.value = true
		flow.submit()
	}

	function destroy() {
		flow?.unmount?.()
		flow = null
		isValid.value = false
		isSubmitting.value = false
	}

	return {
		mount,
		submit,
		destroy,
		completed,
		paymentId,
		error,
		isValid,
		isSubmitting,
	}
}
