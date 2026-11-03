<script setup lang="ts">
import { ref } from 'vue'
import { moveItem } from '@/lib/masterSetup'

const stages = defineModel<string[]>({ required: true })
const dragging = ref<number | null>(null)
const over = ref<number | null>(null)
const announcement = ref('')

function drop(target: number): void {
	if (dragging.value !== null) move(dragging.value, target)
	dragging.value = null
	over.value = null
}

function move(from: number, to: number): void {
	if (to < 0 || to >= stages.value.length || from === to) return
	stages.value = moveItem(stages.value, from, to)
	announcement.value = `${stages.value[to]} moved to position ${to + 1} of ${stages.value.length}.`
}

// Arrow keys move the focused milestone, for people who do not drag.
function onKey(event: KeyboardEvent, index: number): void {
	const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[
		event.key
	]
	if (!step) return
	event.preventDefault()
	const target = index + step
	move(index, target)
	const chips = (event.currentTarget as HTMLElement).parentElement?.children
	;(chips?.[target] as HTMLElement | undefined)?.focus()
}
</script>

<template>
	<div>
		<ul
			class="flex flex-wrap gap-2 rounded-ik-lg bg-ik-panel p-3"
			aria-label="Sales pipeline milestones. Drag, or use the arrow keys, to reorder."
		>
			<li
				v-for="(stage, index) in stages"
				:key="stage"
				draggable="true"
				tabindex="0"
				:aria-label="`${stage}, position ${index + 1} of ${stages.length}`"
				class="flex cursor-grab select-none items-center gap-1.5 rounded-ik-sm px-3 py-1.5 text-ik-label-sm shadow-ik-1 transition-colors focus-visible:shadow-ik-focus focus-visible:outline-none active:cursor-grabbing"
				:class="[
					index === stages.length - 1
						? 'bg-ik-primary-deep text-white'
						: 'bg-white text-ik-text',
					{ 'ring-2 ring-ik-primary': over === index && dragging !== index },
					{ 'opacity-50': dragging === index },
				]"
				@dragstart="dragging = index"
				@dragenter.prevent="over = index"
				@dragover.prevent
				@dragend="dragging = null; over = null"
				@drop.prevent="drop(index)"
				@keydown="onKey($event, index)"
			>
				<span
					v-if="index === stages.length - 1"
					class="lucide-trophy size-3.5"
					aria-hidden="true"
				/>
				<span
					v-else
					class="size-1.5 rounded-full"
					:class="index % 3 === 2 ? 'bg-ik-jade-ink' : 'bg-ik-primary'"
					aria-hidden="true"
				/>
				{{ stage }}
			</li>
		</ul>
		<p class="sr-only" aria-live="polite">{{ announcement }}</p>
	</div>
</template>
