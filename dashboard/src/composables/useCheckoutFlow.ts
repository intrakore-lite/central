import { ref } from 'vue'
import type { CheckoutSetup } from '@/types/onboarding'

// Checkout Flow, Checkout.com's in-page card component. See
// https://www.checkout.com/docs/payments/accept-payments/accept-a-payment-on-your-website
const FLOW_SCRIPT = 'https://checkout-web-components.checkout.com/index.js'

interface FlowComponent {
	mount(element: HTMLElement): void
	unmount?(): void
}

interface CheckoutWebComponents {
	create(name: 'flow'): FlowComponent
}

type CheckoutWebComponentsLoader = (options: {
	publicKey: string
	environment: string
	locale: string
	paymentSession: CheckoutSetup['payment_session']
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

/** Checkout Flow in the card slot. `completed` turns true once Checkout has saved the card. */
export function useCheckoutFlow() {
	const completed = ref(false)
	const paymentId = ref('')
	const error = ref('')
	let flow: FlowComponent | null = null

	async function mount(element: HTMLElement, setup: CheckoutSetup) {
		const load = await loadFlowScript()
		const checkout = await load({
			publicKey: setup.public_key,
			environment: setup.environment,
			locale: 'en',
			paymentSession: setup.payment_session,
			onPaymentCompleted: (_component, payment) => {
				paymentId.value = payment.id
				completed.value = true
			},
			onError: (_component, failure) => {
				error.value =
					failure.message || 'Checkout.com could not save this card.'
			},
		})
		flow = checkout.create('flow')
		flow.mount(element)
	}

	function destroy() {
		flow?.unmount?.()
		flow = null
	}

	return { mount, destroy, completed, paymentId, error }
}
