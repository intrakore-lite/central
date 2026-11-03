<script setup lang="ts">
// The mark a customer of a managed console sees on a site: its product's logo, or a
// neutral globe. It stands where operators see the cloud provider's logo.

withDefaults(
	defineProps<{
		/** The product's logo URL; null shows the globe. */
		logo?: string | null
		size?: number
	}>(),
	{ logo: null, size: 32 },
)
</script>

<template>
	<span
		class="grid shrink-0 place-items-center overflow-hidden rounded-full bg-surface-gray-2"
		:style="{ width: `${size}px`, height: `${size}px` }"
		aria-hidden="true"
	>
		<img v-if="logo" :src="logo" alt="" class="size-full object-contain p-1" />
		<span
			v-else
			class="lucide-globe text-ink-gray-6"
			:style="{ width: `${size / 2}px`, height: `${size / 2}px` }"
		/>
	</span>
</template>
