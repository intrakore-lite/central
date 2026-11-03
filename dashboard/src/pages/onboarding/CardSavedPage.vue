<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PENDING_KEY, SAVED_MESSAGE } from '@/composables/useCardFrame'

const route = useRoute()
const router = useRouter()

// Checkout.com returns with the payment it made for the card, as `cko-payment-id`.
function rememberPaymentId(): void {
	const paymentId = route.query['cko-payment-id']
	if (typeof paymentId !== 'string' || !paymentId) return
	try {
		const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null')
		if (pending)
			sessionStorage.setItem(
				PENDING_KEY,
				JSON.stringify({ ...pending, payment_id: paymentId }),
			)
	} catch {
		// Without the id, Central still finds the card's payment by its reference.
	}
}

// A hosted card page returns here. Inside the billing step's frame, tell that page the card is
// saved. After a full-page redirect, open the billing step, which confirms the card.
onMounted(() => {
	if (window.parent !== window) {
		window.parent.postMessage({ type: SAVED_MESSAGE }, window.location.origin)
		return
	}
	rememberPaymentId()
	router.replace('/onboarding/billing')
})
</script>

<template>
	<main
		class="flex min-h-screen items-center justify-center bg-white p-6 text-center text-base text-ink-gray-7"
	>
		<p>Card saved. Finishing your setup…</p>
	</main>
</template>
