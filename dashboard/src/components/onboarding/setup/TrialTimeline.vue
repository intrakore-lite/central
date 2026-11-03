<script setup lang="ts">
import { computed } from 'vue'
import { money } from '@/lib/format'

interface TrialTimelineProps {
	trialDays: number
	currency: string
	/** The product's own apps by title, such as CRM and Estimation. */
	modules: string[]
	productTitle: string
}

const props = defineProps<TrialTimelineProps>()

const dueToday = computed(() => money(0, props.currency))
const unlocked = computed(() =>
	props.modules.length
		? `Full access unlocked to ${listed(props.modules)}.`
		: `Full access unlocked to ${props.productTitle}.`,
)
const milestones = computed(() => [
	{
		day: 'Day 1 (Today)',
		icon: 'lucide-check',
		tone: 'bg-ik-primary-deep text-white shadow-ik-1',
	},
	{
		day: `Day ${props.trialDays - 1}`,
		text: 'Courtesy reminder email sent before the trial ends.',
		icon: 'lucide-mail',
		tone: 'bg-ik-primary-soft text-ik-primary-deep',
	},
	{
		day: `Day ${props.trialDays}`,
		text: 'First monthly subscription debit begins automatically.',
		icon: 'lucide-credit-card',
		tone: 'bg-ik-chip-hover text-ik-muted',
	},
])

// "CRM, Estimation & AI": a short list reads better than a comma chain.
function listed(names: string[]): string {
	const shown = names.slice(0, 3)
	const rest = names.length - shown.length
	if (rest > 0) return `${shown.join(', ')} and ${rest} more modules`
	if (shown.length === 1) return `the ${shown[0]} module`
	return `${shown.slice(0, -1).join(', ')} & ${shown[shown.length - 1]} modules`
}
</script>

<template>
	<section
		class="relative overflow-hidden rounded-ik-lg bg-white p-6 shadow-ik-2 md:p-7"
		aria-labelledby="trial-title"
	>
		<div
			class="pointer-events-none absolute -right-12 -top-12 size-48 rounded-full bg-ik-primary-soft/40 blur-2xl"
			aria-hidden="true"
		/>
		<div
			class="relative flex flex-col justify-between gap-4 pb-6 sm:flex-row sm:items-center"
		>
			<div>
				<p class="mb-1 text-ik-kicker uppercase text-ik-primary">
					Instant Activation
				</p>
				<h2 id="trial-title" class="text-ik-title text-ik-ink">
					Zero Charge Today — {{ trialDays }} Days Free Trial
				</h2>
				<p class="mt-0.5 text-ik-body-sm text-ik-slate">
					Explore {{ productTitle }} with your whole team, completely
					unrestricted.
				</p>
			</div>
			<div class="shrink-0 text-left sm:text-right">
				<span
					class="block text-ik-display-mobile text-ik-primary md:text-ik-display"
				>
					{{ dueToday }}
				</span>
				<span class="text-ik-label-sm text-ik-slate">Due right now</span>
			</div>
		</div>

		<div class="relative pt-6">
			<div
				class="absolute left-4 right-4 top-10 hidden h-0.5 bg-ik-line sm:block"
				aria-hidden="true"
			/>
			<ol class="relative z-10 grid grid-cols-1 gap-5 sm:grid-cols-3">
				<li
					v-for="(milestone, index) in milestones"
					:key="milestone.day"
					class="flex items-start gap-3 sm:flex-col sm:gap-2"
				>
					<span
						class="flex size-8 shrink-0 items-center justify-center rounded-full"
						:class="milestone.tone"
						aria-hidden="true"
					>
						<span class="size-4" :class="milestone.icon" />
					</span>
					<div>
						<p class="text-ik-label font-bold text-ik-text">
							{{ milestone.day }}
						</p>
						<p class="mt-0.5 text-ik-body-sm text-ik-slate">
							<template v-if="index === 0">
								{{ unlocked }}
								<strong class="font-bold text-ik-text">
									{{ dueToday }}
									charged</strong
								>.
							</template>
							<template v-else>{{ milestone.text }}</template>
						</p>
					</div>
				</li>
			</ol>
		</div>

		<p
			class="relative mt-6 flex items-center gap-3 rounded-ik-md bg-ik-panel p-3.5 text-ik-body-sm text-ik-muted"
		>
			<span
				class="lucide-shield-check size-5 shrink-0 text-ik-primary"
				aria-hidden="true"
			/>
			<span>
				<strong class="font-semibold text-ik-text"
					>No lock-in commitment:</strong
				>
				Cancel anytime before Day {{ trialDays }} in
				<span class="text-ik-primary underline decoration-dotted"
					>Settings &gt; Billing</span
				>
				and nothing is charged.
			</span>
		</p>
	</section>
</template>
