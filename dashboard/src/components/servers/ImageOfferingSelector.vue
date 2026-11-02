<script setup lang="ts">
import { computed } from 'vue'
import appsLogo from '@/assets/images/apps.svg'
import ubuntuLogo from '@/assets/images/ubuntu.svg'
import ChoiceCards from '@/components/common/ChoiceCards.vue'
import { brand } from '@/lib/brand'
import type { ProductApp } from '@/types/serverCreation'

interface ImageChoice {
	label: string
	value: string
	description?: string
	logo: string | null
	apps?: ProductApp[]
}

const props = defineProps<{
	modelValue: string
	options: ImageChoice[]
	disabled?: boolean
}>()

// A product card lists its apps, which needs room: two wide columns, top-aligned.
const hasApps = computed(() =>
	props.options.some((option) => option.apps?.length),
)

function ownApps(option: ImageChoice): ProductApp[] {
	return (option.apps ?? []).filter((app) => !app.is_core)
}

function hasCore(option: ImageChoice): boolean {
	return (option.apps ?? []).some((app) => app.is_core)
}

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const defaultLogos: Record<string, string> = {
	apps: appsLogo,
	pilot: brand.logo,
	ubuntu: ubuntuLogo,
}

function logoFor(option: ImageChoice): string | null {
	return option.logo || defaultLogos[option.value] || null
}
</script>

<template>
	<div>
		<ChoiceCards
			:model-value="modelValue"
			:options="options"
			:disabled="disabled"
			:columns="hasApps || options.length <= 2 ? 2 : 3"
			:class="{ 'items-start': hasApps }"
			label="Select an image"
			@update:model-value="emit('update:modelValue', $event)"
		>
			<template #details="{ option }">
				<ul
					v-if="(option as ImageChoice).apps?.length"
					class="mt-1.5 flex flex-wrap gap-1"
					aria-label="Included apps"
				>
					<li
						v-for="app in ownApps(option as ImageChoice)"
						:key="app.app"
						class="rounded-4 bg-surface-gray-2 px-1.5 py-0.5 text-p-xs text-ink-gray-7"
						:title="app.version ? `${app.title} ${app.version}` : app.title"
					>
						{{ app.title }}
						<span v-if="app.version" class="text-ink-gray-5"
							>{{ app.version }}</span
						>
					</li>
					<li
						v-if="hasCore(option as ImageChoice)"
						class="rounded-4 px-1.5 py-0.5 text-p-xs text-ink-gray-5"
					>
						+ Core
					</li>
				</ul>
			</template>
			<template #icon="{ option }">
				<img
					v-if="logoFor(option as ImageChoice)"
					:src="logoFor(option as ImageChoice) ?? ''"
					alt=""
					class="size-6 shrink-0 object-contain"
					draggable="false"
				/>
				<span
					v-else
					class="grid size-6 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-ink-gray-8"
					aria-hidden="true"
					>{{ option.label.charAt(0) }}</span
				>
			</template>
		</ChoiceCards>
		<p v-if="!options.length" class="text-p-sm text-ink-gray-5">
			No server images are configured. Contact support to check image
			availability.
		</p>
	</div>
</template>
