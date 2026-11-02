<script setup lang="ts">
import { computed } from 'vue'
import { useProduct } from '@/composables/useProduct'
import {
	signInShowcase,
	trialDays,
	trialOffer,
	trialShowcase,
	trustLine,
} from '@/lib/brand'

const { product, productKey } = useProduct()

// A signup link that names a product is a free trial. Every other auth page is a sign-in.
const showcase = computed(() => {
	if (!productKey.value) return signInShowcase
	const title =
		product.value?.title ??
		(trialOffer?.product === productKey.value ? trialOffer.title : null)
	return title
		? trialShowcase(title, trialDays(productKey.value))
		: signInShowcase
})
</script>

<template>
	<aside
		class="sticky top-0 hidden h-screen w-1/2 flex-col gap-10 overflow-hidden bg-gradient-to-b from-blueprint-50 to-blueprint-100 px-14 py-16 md:flex"
	>
		<div class="max-w-[520px] space-y-4">
			<p class="text-sm-semibold uppercase tracking-wide text-blueprint-700">
				{{ showcase.eyebrow }}
			</p>
			<h2 class="text-7xl-semibold leading-tight text-blueprint-900">
				{{ showcase.headline }}
			</h2>
			<p class="text-p-lg text-blueprint-900/75">{{ showcase.summary }}</p>
		</div>

		<!-- The product shots have a white ground, so they sit on a card. -->
		<div
			class="flex min-h-0 flex-1 items-center justify-center rounded-7 bg-white p-6 shadow-xl"
		>
			<img
				:src="showcase.image"
				alt=""
				class="max-h-full max-w-full object-contain"
			/>
		</div>

		<p class="flex items-center gap-2 text-p-base-medium text-blueprint-800">
			<span class="lucide-shield-check size-4 shrink-0" aria-hidden="true" />
			{{ trustLine }}
		</p>
	</aside>
</template>
