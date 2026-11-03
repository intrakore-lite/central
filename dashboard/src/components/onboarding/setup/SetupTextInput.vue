<script setup lang="ts">
interface SetupTextInputProps {
	id: string
	/** A lucide icon class, such as lucide-user. */
	icon: string
	type?: string
	placeholder?: string
	autocomplete?: string
	readonly?: boolean
	invalid?: boolean
	maxlength?: number
}

withDefaults(defineProps<SetupTextInputProps>(), { type: 'text' })
const model = defineModel<string>({ required: true })
</script>

<template>
	<div class="relative flex items-center">
		<span
			class="pointer-events-none absolute left-3.5 size-5 text-ik-slate"
			:class="icon"
			aria-hidden="true"
		/>
		<input
			:id="id"
			v-model="model"
			:type="type"
			:placeholder="placeholder"
			:autocomplete="autocomplete"
			:readonly="readonly"
			:maxlength="maxlength"
			:aria-invalid="invalid || undefined"
			class="h-12 w-full rounded-ik-md border-0 bg-white pl-11 pr-4 text-ik-body text-ik-text shadow-ik-control transition-shadow placeholder:text-ik-placeholder focus:shadow-ik-focus focus:outline-none focus:ring-0 read-only:bg-ik-canvas-soft read-only:text-ik-muted"
			:class="{ 'shadow-ik-invalid': invalid }"
		/>
	</div>
</template>
