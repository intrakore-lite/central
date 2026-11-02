<script setup lang="ts">
import { Button } from 'frappe-ui'

interface AuthSubmitButtonProps {
	loading?: boolean
	disabled?: boolean
}

withDefaults(defineProps<AuthSubmitButtonProps>(), {
	loading: false,
	disabled: false,
})
</script>

<template>
	<!-- The brand blue replaces the gray of the solid variant on the auth pages only. -->
	<Button
		type="submit"
		variant="solid"
		size="md"
		class="w-full !bg-blueprint-700 !text-white hover:!bg-blueprint-800 active:!bg-blueprint-900 disabled:!bg-blueprint-200"
		:loading="loading"
		:disabled="disabled"
	>
		<slot />
	</Button>
</template>
