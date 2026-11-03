<script setup lang="ts">
interface SetupSelectProps {
	id: string
	/** A lucide icon class, such as lucide-hard-hat. */
	icon: string
	options: string[]
	placeholder: string
	invalid?: boolean
}

defineProps<SetupSelectProps>()
const model = defineModel<string>({ required: true })
</script>

<template>
	<div class="relative flex items-center">
		<span
			class="pointer-events-none absolute left-3.5 size-5 text-ik-slate"
			:class="icon"
			aria-hidden="true"
		/>
		<select
			:id="id"
			v-model="model"
			:aria-invalid="invalid || undefined"
			class="h-12 w-full cursor-pointer appearance-none truncate rounded-ik-md border-0 bg-white bg-none pl-11 pr-10 text-ik-body shadow-ik-control transition-shadow focus:shadow-ik-focus focus:outline-none focus:ring-0"
			:class="[
				model ? 'text-ik-text' : 'text-ik-placeholder',
				{ 'shadow-ik-invalid': invalid },
			]"
		>
			<option value="" disabled>{{ placeholder }}</option>
			<option
				v-for="option in options"
				:key="option"
				:value="option"
				class="text-ik-text"
			>
				{{ option }}
			</option>
		</select>
		<span
			class="lucide-chevrons-up-down pointer-events-none absolute right-3.5 size-[18px] text-ik-slate"
			aria-hidden="true"
		/>
	</div>
</template>
