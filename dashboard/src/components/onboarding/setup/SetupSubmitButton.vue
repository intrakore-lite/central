<script setup lang="ts">
import { LoadingIndicator } from 'frappe-ui'

interface SetupSubmitButtonProps {
	label: string
	loading?: boolean
	disabled?: boolean
}

defineProps<SetupSubmitButtonProps>()
</script>

<template>
	<button
		type="submit"
		class="group flex h-12 w-full items-center justify-center gap-2 rounded-ik-md bg-ik-primary px-4 text-ik-label-lg font-bold text-white shadow-ik-button transition-all hover:bg-ik-primary-hover focus-visible:shadow-ik-3 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
		:disabled="loading || disabled"
		:aria-busy="loading || undefined"
	>
		<LoadingIndicator v-if="loading" class="size-4 text-white" />
		<span>{{ label }}</span>
		<span
			v-if="!loading"
			class="lucide-arrow-right size-5 transition-transform group-hover:translate-x-1"
			aria-hidden="true"
		/>
	</button>
</template>
