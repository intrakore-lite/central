// Checkout.com Flow: the card form Checkout.com draws on our page.
//
// The card data goes from the customer to Checkout.com only, so PCI scope stays
// with Checkout.com. The backend opens the payment session and returns it with
// the public key and the environment (see CheckoutOrder). This mounts Flow with
// that session and resolves when Checkout.com reports the payment complete. The
// caller then confirms server-side: Central reads the payment back from
// Checkout.com by the reference it gave the session, never from the browser.

import type { CheckoutOrder } from '@/lib/gateway'
import { loadScript } from '@/lib/gateway'

// Checkout.com says to load Flow from its own host, never bundled or self-hosted.
const FLOW_SCRIPT_URL = 'https://checkout-web-components.checkout.com/index.js'

interface FlowComponent {
	mount: (el: string | Element) => unknown
	unmount?: () => void
}

interface CheckoutWebComponentsInstance {
	create: (name: 'flow', options?: Record<string, unknown>) => FlowComponent
}

type CheckoutWebComponentsFactory = (
	options: Record<string, unknown>,
) => Promise<CheckoutWebComponentsInstance>

declare global {
	interface Window {
		CheckoutWebComponents?: CheckoutWebComponentsFactory
	}
}

export interface FlowCallbacks {
	/** Checkout.com approved the payment or verified the card. */
	onCompleted: (paymentId: string) => void
	onError: (error: unknown) => void
	onReady?: () => void
}

export interface MountedFlow {
	destroy: () => void
}

export async function mountCheckoutFlow(
	el: Element,
	order: CheckoutOrder,
	{ onCompleted, onError, onReady }: FlowCallbacks,
): Promise<MountedFlow> {
	if (!order.public_key || !order.payment_session)
		throw new Error(
			'The card form cannot start because the payment session is missing. Contact support.',
		)
	await loadScript(order.flow_script_url || FLOW_SCRIPT_URL)
	if (!window.CheckoutWebComponents)
		throw new Error(
			'The Checkout.com card form could not load. Check your connection and try again.',
		)
	const checkout = await window.CheckoutWebComponents({
		publicKey: order.public_key,
		environment: order.environment || 'sandbox',
		paymentSession: order.payment_session,
		locale: document.documentElement.lang || undefined,
		onReady: () => onReady?.(),
		onPaymentCompleted: (_component: unknown, response: { id?: string }) =>
			onCompleted(response?.id || ''),
		onError: (_component: unknown, error: unknown) => onError(error),
	})
	const flow = checkout.create('flow')
	flow.mount(el)
	return { destroy: () => flow.unmount?.() }
}
