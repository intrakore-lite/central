<script setup lang="ts">
import { Badge } from 'frappe-ui'
import type { ProductApp } from '@/types/serverCreation'

interface Resource {
	type: string
	value: string
}

interface Props {
	plan?: string
	server: string
	price: string
	cycle?: string
	resources: Resource[]
	/** The apps of the chosen product, without the core apps. */
	apps?: ProductApp[]
	tags: string[]
}

withDefaults(defineProps<Props>(), { apps: () => [] })

const tiles = [
	{ type: 'Compute', label: 'vCPU', icon: 'lucide-cpu' },
	{ type: 'Memory', label: 'Memory', icon: 'lucide-memory-stick' },
	{ type: 'Disk', label: 'SSD', icon: 'lucide-database' },
]
</script>

<template>
	<section class="space-y-5 border-t border-outline-gray-1 p-6">
		<p class="text-sm text-ink-gray-5">Summary</p>
		<div class="flex items-center justify-between gap-4">
			<div class="min-w-0 space-y-1.5">
				<h2 class="truncate text-2xl-semibold text-ink-gray-9">
					{{ plan ? `${plan} plan` : 'No plan selected' }}
				</h2>
				<p class="truncate text-base text-ink-gray-5">{{ server }}</p>
			</div>
			<p class="shrink-0 text-4xl-semibold text-ink-gray-9">
				{{ price }}
				<span v-if="cycle" class="text-lg text-ink-gray-5">/{{ cycle }}</span>
			</p>
		</div>

		<dl
			class="grid grid-cols-2 divide-outline-gray-2 rounded-6 border border-outline-gray-2 md:grid-cols-3 md:divide-x"
		>
			<div
				v-for="tile in tiles"
				:key="tile.type"
				class="flex items-center gap-3 px-4 py-4"
			>
				<span
					class="grid size-10 shrink-0 place-items-center rounded-6 bg-surface-gray-1"
					aria-hidden="true"
				>
					<span :class="[tile.icon, 'size-5 text-ink-gray-6']" />
				</span>
				<div class="min-w-0">
					<dd class="truncate text-xl-semibold text-ink-gray-9">
						{{ resources.find((r) => r.type === tile.type)?.value ?? '—' }}
					</dd>
					<dt class="text-base text-ink-gray-5">{{ tile.label }}</dt>
				</div>
			</div>
		</dl>

		<div v-if="apps.length" class="space-y-2">
			<p class="text-sm text-ink-gray-5">Included apps</p>
			<ul class="flex flex-wrap gap-2">
				<li
					v-for="app in apps"
					:key="app.app"
					class="rounded-5 border border-outline-gray-2 px-2 py-1 text-base text-ink-gray-8"
				>
					{{ app.title }}
					<span v-if="app.version" class="text-sm text-ink-gray-5"
						>{{ app.version }}</span
					>
				</li>
			</ul>
		</div>

		<div class="flex flex-wrap gap-2">
			<Badge
				v-for="tag in tags"
				:key="tag"
				:label="tag"
				variant="outline"
				size="lg"
			/>
		</div>

		<slot />
	</section>
</template>
