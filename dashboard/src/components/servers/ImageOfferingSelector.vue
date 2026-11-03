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

// A product card lists its apps in two wide columns. Every card keeps one row of
// chips, so a bundle of 25 apps is as tall as a bundle of 5.
const hasApps = computed(() =>
	props.options.some((option) => option.apps?.length),
)

const SHOWN_APPS = 3

// How many products include each app. The apps that few products have tell the
// products apart, so they come first; AI and Accounting are in nearly all of them.
const appCounts = computed(() => {
	const counts = new Map<string, number>()
	for (const option of props.options) {
		for (const app of ownApps(option)) {
			counts.set(app.app, (counts.get(app.app) ?? 0) + 1)
		}
	}
	return counts
})

function ownApps(option: ImageChoice): ProductApp[] {
	return (option.apps ?? []).filter((app) => !app.is_core)
}

function rankedApps(option: ImageChoice): ProductApp[] {
	const counts = appCounts.value
	return ownApps(option)
		.map((app, index) => ({ app, index }))
		.sort(
			(a, b) =>
				(counts.get(a.app.app) ?? 0) - (counts.get(b.app.app) ?? 0) ||
				a.index - b.index,
		)
		.map(({ app }) => app)
}

function shownApps(option: ImageChoice): ProductApp[] {
	return rankedApps(option).slice(0, SHOWN_APPS)
}

function hiddenApps(option: ImageChoice): ProductApp[] {
	return rankedApps(option).slice(SHOWN_APPS)
}

function appLabel(app: ProductApp): string {
	return app.version ? `${app.title} ${app.version}` : app.title
}

function allAppsLabel(option: ImageChoice): string {
	const names = ownApps(option).map(appLabel)
	if (hasCore(option)) names.push('Core')
	return names.join(', ')
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
			label="Select an image"
			@update:model-value="emit('update:modelValue', $event)"
		>
			<template #details="{ option }">
				<ul
					v-if="(option as ImageChoice).apps?.length"
					class="mt-1.5 flex flex-nowrap items-center gap-1 overflow-hidden"
					:aria-label="`Included apps: ${allAppsLabel(option as ImageChoice)}`"
					:title="allAppsLabel(option as ImageChoice)"
				>
					<li
						v-for="app in shownApps(option as ImageChoice)"
						:key="app.app"
						class="min-w-0 truncate rounded-4 bg-surface-gray-2 px-1.5 py-0.5 text-p-xs text-ink-gray-7"
					>
						{{ app.title }}
					</li>
					<li
						v-if="hiddenApps(option as ImageChoice).length"
						class="shrink-0 rounded-4 px-1.5 py-0.5 text-p-xs text-ink-gray-5"
					>
						+{{ hiddenApps(option as ImageChoice).length }}
						more
					</li>
					<li
						v-else-if="hasCore(option as ImageChoice)"
						class="shrink-0 rounded-4 px-1.5 py-0.5 text-p-xs text-ink-gray-5"
					>
						+ Core
					</li>
				</ul>
				<p
					v-if="(option as ImageChoice).apps?.length"
					class="mt-1 text-p-xs text-ink-gray-5"
				>
					{{ ownApps(option as ImageChoice).length }}
					apps
				</p>
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
