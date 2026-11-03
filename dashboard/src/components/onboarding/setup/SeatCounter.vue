<script setup lang="ts">
import { computed } from 'vue'
import { money } from '@/lib/format'
import type { SeatPricing, SeatQuote } from '@/types/onboarding'

interface SeatCounterProps {
	/** The product the seats are for, such as CRM + Estimation. */
	productTitle: string
	pricing: SeatPricing
	quote: SeatQuote | null
}

const props = defineProps<SeatCounterProps>()
const seats = defineModel<number>({ required: true })

const monthly = computed(() =>
	props.quote && props.quote.monthly > 0
		? money(props.quote.monthly, props.pricing.currency)
		: null,
)

function change(step: number) {
	seats.value = Math.min(
		props.pricing.max_seats,
		Math.max(1, seats.value + step),
	)
}
</script>

<template>
	<div class="flex flex-col gap-3 rounded-ik-md bg-ik-panel p-4">
		<div class="flex items-center justify-between gap-4">
			<div>
				<p id="seat-count-label" class="text-ik-label font-bold text-ik-text">
					{{ productTitle }}
					seats
				</p>
				<p class="text-ik-body-sm text-ik-muted">
					One seat per named user. Every seat is free for
					{{ pricing.trial_days }}
					days.
				</p>
			</div>
			<div
				class="flex shrink-0 items-center gap-2 rounded-ik-sm bg-white px-2 py-1 shadow-ik-1"
				role="group"
				aria-labelledby="seat-count-label"
			>
				<button
					type="button"
					class="flex size-8 items-center justify-center rounded text-ik-text transition-colors hover:bg-ik-chip focus-visible:shadow-ik-focus focus-visible:outline-none disabled:opacity-40"
					aria-label="Remove a seat"
					:disabled="seats <= 1"
					@click="change(-1)"
				>
					<span class="lucide-minus size-4" aria-hidden="true" />
				</button>
				<output
					class="w-8 text-center text-ik-title font-bold text-ik-primary"
					aria-live="polite"
				>
					{{ seats }}
				</output>
				<button
					type="button"
					class="flex size-8 items-center justify-center rounded text-ik-text transition-colors hover:bg-ik-chip focus-visible:shadow-ik-focus focus-visible:outline-none disabled:opacity-40"
					aria-label="Add a seat"
					:disabled="seats >= pricing.max_seats"
					@click="change(1)"
				>
					<span class="lucide-plus size-4" aria-hidden="true" />
				</button>
			</div>
		</div>
		<div
			class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 pt-2 text-ik-label-sm text-ik-muted"
		>
			<span class="flex items-center gap-1">
				<span class="size-2 rounded-full bg-ik-jade" aria-hidden="true" />
				After the trial:
				<strong v-if="monthly" class="ml-1 font-semibold text-ik-text">
					{{ monthly }}
					/ month + {{ pricing.vat_percent }}% VAT
				</strong>
				<strong v-else class="ml-1 font-semibold text-ik-text">
					price on request
				</strong>
			</span>
			<span v-if="pricing.included_seats">
				The base plan includes {{ pricing.included_seats }} seats
			</span>
		</div>
	</div>
</template>
