<script setup lang="ts">
import { brand } from '@/lib/brand'
</script>

<template>
	<p v-if="brand.policiesUrl" class="text-center text-p-sm text-ink-gray-5">
		By continuing, you agree to our
		<a
			class="text-p-sm-medium text-ink-gray-8 hover:underline"
			:href="brand.policiesUrl"
			target="_blank"
			rel="noopener noreferrer"
		>
			Terms and Policies</a
		>
	</p>
</template>
