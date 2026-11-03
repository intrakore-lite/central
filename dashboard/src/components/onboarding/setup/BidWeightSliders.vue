<script setup lang="ts">
import { computed } from 'vue'
import {
	rebalanceWeights,
	WEIGHT_LABELS,
	type WeightKey,
	type Weights,
	weightTotal,
} from '@/lib/masterSetup'

const weights = defineModel<Weights>({ required: true })
const threshold = defineModel<number>('threshold', { required: true })

const total = computed(() => weightTotal(weights.value))

function setWeight(key: WeightKey, event: Event): void {
	const value = Number((event.target as HTMLInputElement).value)
	weights.value = rebalanceWeights(weights.value, key, value)
}

function setThreshold(event: Event): void {
	threshold.value = Number((event.target as HTMLInputElement).value)
}
</script>

<template>
	<div class="flex flex-col gap-4 rounded-ik-lg bg-ik-panel p-4">
		<div
			v-for="{ key, label } in WEIGHT_LABELS"
			:key="key"
			class="flex flex-col gap-1.5"
		>
			<div
				class="flex items-center justify-between text-ik-body-sm text-ik-text"
			>
				<label :for="`weight-${key}`">{{ label }}</label>
				<span class="text-ik-label-sm text-ik-primary"
					>{{ weights[key] }}%</span
				>
			</div>
			<input
				:id="`weight-${key}`"
				type="range"
				min="0"
				max="100"
				step="5"
				:value="weights[key]"
				class="ik-range"
				:style="{ '--fill': `${weights[key]}%` }"
				@input="setWeight(key, $event)"
			/>
		</div>
		<div class="flex items-center justify-between border-t border-ik-line pt-3">
			<span class="text-ik-label-sm text-ik-slate">
				Total
				<span :class="total === 100 ? 'text-ik-jade-ink' : 'text-ik-error'"
					>{{ total }}%</span
				>
			</span>
			<label
				for="bid-threshold"
				class="flex items-center gap-3 text-ik-label-sm text-ik-slate"
			>
				Win score threshold
				<input
					id="bid-threshold"
					type="range"
					min="40"
					max="95"
					step="5"
					:value="threshold"
					class="ik-range w-28"
					:style="{ '--fill': `${((threshold - 40) / 55) * 100}%` }"
					@input="setThreshold"
				/>
				<span class="w-9 text-right text-ik-primary">{{ threshold }}%</span>
			</label>
		</div>
	</div>
</template>

<style scoped>
.ik-range {
	appearance: none;
	height: 6px;
	border-radius: 9999px;
	background: linear-gradient(
		to right,
		#0016a7 var(--fill),
		#dee2ee var(--fill)
	);
	cursor: pointer;
}
.ik-range:focus-visible {
	outline: none;
	box-shadow: 0 0 0 4px rgba(0, 34, 230, 0.12);
}
.ik-range::-webkit-slider-thumb {
	appearance: none;
	width: 16px;
	height: 16px;
	border-radius: 9999px;
	background: #fff;
	border: 3px solid #0022e6;
}
.ik-range::-moz-range-thumb {
	width: 12px;
	height: 12px;
	border-radius: 9999px;
	background: #fff;
	border: 3px solid #0022e6;
}
</style>
