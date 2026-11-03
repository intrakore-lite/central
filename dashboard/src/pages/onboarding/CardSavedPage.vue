<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { SAVED_MESSAGE } from '@/composables/useCardFrame'

const router = useRouter()

// A hosted card page returns here. Inside the billing step's frame, tell that page the card is
// saved. After a full-page redirect, open the billing step, which confirms the card.
onMounted(() => {
	if (window.parent !== window) {
		window.parent.postMessage({ type: SAVED_MESSAGE }, window.location.origin)
		return
	}
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
