<script setup lang="ts">
interface ChoiceChipsProps {
	/** The accessible name of the group. */
	label: string
	options: string[]
	/** An optional choice can be cleared by choosing it again. */
	clearable?: boolean
	invalid?: boolean
}

const props = defineProps<ChoiceChipsProps>()
const model = defineModel<string>({ required: true })

function choose(option: string) {
	model.value = props.clearable && model.value === option ? '' : option
}
</script>

<template>
	<div
		role="radiogroup"
		:aria-label="label"
		:aria-invalid="invalid || undefined"
		class="grid gap-2"
		:style="{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }"
	>
		<button
			v-for="option in options"
			:key="option"
			type="button"
			role="radio"
			:aria-checked="model === option"
			class="min-h-11 rounded-ik-sm px-1 py-2.5 text-center text-ik-label-sm transition-colors sm:text-ik-label focus-visible:shadow-ik-focus focus-visible:outline-none"
			:class="
				model === option
					? 'bg-ik-primary-deep font-bold text-white shadow-ik-1'
					: 'bg-ik-chip text-ik-muted hover:bg-ik-chip-hover'
			"
			@click="choose(option)"
		>
			{{ option }}
		</button>
	</div>
</template>
