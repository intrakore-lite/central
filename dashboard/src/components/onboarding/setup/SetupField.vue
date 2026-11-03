<script setup lang="ts">
interface SetupFieldProps {
	/** The id of the control the label names. */
	for?: string
	label: string
	/** A field validation message, shown under the control. */
	error?: string
}

defineProps<SetupFieldProps>()
</script>

<template>
	<div class="flex flex-col gap-1.5">
		<div class="flex items-center justify-between gap-2">
			<label :for="$props.for" class="text-ik-label text-ik-text">
				{{ label }}
			</label>
			<slot name="aside" />
		</div>
		<slot />
		<p v-if="error" class="text-ik-body-sm text-ik-error" role="alert">
			{{ error }}
		</p>
	</div>
</template>
