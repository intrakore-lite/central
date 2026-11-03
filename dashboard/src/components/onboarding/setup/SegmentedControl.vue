<script setup lang="ts" generic="T extends string">
interface SegmentedOption<V> {
	value: V
	label: string
}

interface SegmentedControlProps<V> {
	/** The accessible name of the group. */
	label: string
	options: SegmentedOption<V>[]
	disabled?: boolean
}

defineProps<SegmentedControlProps<T>>()
const model = defineModel<T>({ required: true })
</script>

<template>
	<div
		role="radiogroup"
		:aria-label="label"
		class="flex items-center gap-1.5 rounded-ik-md bg-ik-panel p-1"
	>
		<button
			v-for="option in options"
			:key="option.value"
			type="button"
			role="radio"
			:aria-checked="model === option.value"
			:disabled="disabled"
			class="min-h-9 flex-1 rounded-ik-sm px-2 py-1.5 text-center text-ik-label-sm transition-colors focus-visible:shadow-ik-focus focus-visible:outline-none disabled:cursor-not-allowed"
			:class="
				model === option.value
					? 'bg-ik-primary font-bold text-white shadow-ik-1'
					: 'text-ik-muted hover:bg-white hover:text-ik-text'
			"
			@click="model = option.value"
		>
			{{ option.label }}
		</button>
	</div>
</template>
