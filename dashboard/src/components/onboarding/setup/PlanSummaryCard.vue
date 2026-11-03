<script setup lang="ts">
import { computed } from 'vue'
import { money } from '@/lib/format'
import type { SeatPricing, SeatQuote } from '@/types/onboarding'

interface PlanSummaryCardProps {
	productTitle: string
	modules: string[]
	seats: number
	pricing: SeatPricing
	quote: SeatQuote | null
}

const props = defineProps<PlanSummaryCardProps>()

// A bundle such as Intrakore Complete carries many apps. The card lists a few and counts the rest.
const SHOWN_MODULES = 3
const MODULE_ICONS = ['lucide-file-text', 'lucide-calculator', 'lucide-layers']

const shownModules = computed(() => props.modules.slice(0, SHOWN_MODULES))
const moreModules = computed(() => props.modules.length - SHOWN_MODULES)
const hasPrice = computed(() => Boolean(props.quote && props.quote.monthly > 0))
const format = (amount: number) => money(amount, props.pricing.currency)
</script>

<template>
	<section
		class="relative overflow-hidden rounded-ik-lg bg-white p-6 shadow-ik-2"
		aria-labelledby="plan-title"
	>
		<div class="flex items-center justify-between gap-3 pb-4">
			<div>
				<p class="text-ik-kicker uppercase text-ik-primary">Plan Summary</p>
				<h3 id="plan-title" class="text-ik-title text-ik-ink">
					{{ productTitle }}
				</h3>
			</div>
			<span
				class="shrink-0 rounded-full bg-ik-jade-soft px-2.5 py-1 text-ik-label-sm font-bold text-ik-jade-ink"
			>
				{{ pricing.trial_days }}
				Days Free
			</span>
		</div>

		<ul class="space-y-3.5 pt-2">
			<li
				v-for="(module, index) in shownModules"
				:key="module"
				class="flex items-center gap-3 rounded-ik-md bg-ik-panel p-3"
			>
				<span
					class="flex size-8 shrink-0 items-center justify-center rounded-ik-sm bg-ik-primary-soft/60 text-ik-primary-deep"
					aria-hidden="true"
				>
					<span class="size-[18px]" :class="MODULE_ICONS[index]" />
				</span>
				<span class="flex-1 text-ik-label font-bold text-ik-text">
					{{ module }}
				</span>
				<span class="text-ik-label-sm text-ik-slate">Included</span>
			</li>
			<li v-if="moreModules > 0" class="px-3 text-ik-body-sm text-ik-slate">
				+ {{ moreModules }} more modules included
			</li>
			<li class="flex items-start gap-3 rounded-ik-md bg-ik-panel p-3">
				<span
					class="flex size-8 shrink-0 items-center justify-center rounded-ik-sm bg-ik-primary-soft/60 text-ik-primary-deep"
					aria-hidden="true"
				>
					<span class="lucide-users size-[18px]" />
				</span>
				<div class="flex-1">
					<div class="flex items-center justify-between gap-2">
						<span class="text-ik-label font-bold text-ik-text">
							{{ seats }} {{ seats === 1 ? 'Seat' : 'Seats' }}
						</span>
						<span class="text-ik-label-sm text-ik-slate">Expandable</span>
					</div>
					<p class="text-ik-body-sm text-ik-slate">
						Named users for your team. Change the count in Settings &gt;
						Billing.
					</p>
				</div>
			</li>
		</ul>

		<dl class="mt-6 space-y-2.5 pt-5 text-ik-body-sm text-ik-slate">
			<div class="flex items-center justify-between gap-3">
				<dt>
					Monthly rate after the trial
					<template v-if="hasPrice && quote"
						>({{ quote.billed_seats }}
						seats)</template
					>
				</dt>
				<dd class="font-medium text-ik-text">
					{{ hasPrice && quote ? `${format(quote.monthly)} / mo` : 'On request' }}
				</dd>
			</div>
			<div class="flex items-center justify-between gap-3">
				<dt>VAT {{ pricing.vat_percent }}% (estimate)</dt>
				<dd class="font-medium text-ik-text">
					{{ hasPrice && quote ? format(quote.vat) : '—' }}
				</dd>
			</div>
			<div class="flex items-center justify-between gap-3">
				<dt>{{ pricing.trial_days }}-day free trial</dt>
				<dd class="font-bold text-ik-jade-ink">
					{{ hasPrice && quote ? `−${format(quote.total)}` : 'Applied' }}
				</dd>
			</div>
			<div class="flex items-baseline justify-between gap-3 pt-4">
				<dt>
					<span class="block text-ik-title text-ik-text">Total Due Today</span>
					<span>First scheduled debit on Day {{ pricing.trial_days }}</span>
				</dt>
				<dd
					class="whitespace-nowrap text-ik-display-mobile text-ik-jade-ink md:text-ik-display"
				>
					{{ format(0) }}
				</dd>
			</div>
		</dl>
	</section>
</template>
