<script setup lang="ts">
import type { TrustContent } from '@/types/onboarding'

interface TrustProofCardProps {
	trust: TrustContent
}

defineProps<TrustProofCardProps>()
</script>

<template>
	<section class="flex flex-col gap-4 rounded-ik-lg bg-white p-6 shadow-ik-1">
		<div class="flex items-center gap-3">
			<span
				class="flex size-10 shrink-0 items-center justify-center rounded-ik-md bg-ik-jade-soft text-ik-jade-ink"
				aria-hidden="true"
			>
				<span class="lucide-building-2 size-6" />
			</span>
			<div>
				<p class="text-ik-label font-bold text-ik-text">
					{{ trust.proof.title }}
				</p>
				<p class="text-ik-body-sm text-ik-slate">{{ trust.proof.text }}</p>
			</div>
		</div>

		<template v-if="trust.quote">
			<blockquote
				class="rounded-ik-md bg-ik-panel p-4 text-ik-body-sm italic leading-relaxed text-ik-text"
			>
				“{{ trust.quote.text }}”
			</blockquote>
			<div class="flex flex-col pt-1">
				<span class="text-ik-label font-bold text-ik-text">
					{{ trust.quote.author }}
				</span>
				<span v-if="trust.quote.role" class="text-ik-label-sm text-ik-slate">
					{{ trust.quote.role }}
				</span>
			</div>
		</template>
		<ul
			v-else
			class="space-y-2.5 rounded-ik-md bg-ik-panel p-4 text-ik-body-sm text-ik-text"
		>
			<li
				v-for="benefit in trust.benefits"
				:key="benefit"
				class="flex items-start gap-2"
			>
				<span
					class="lucide-circle-check mt-0.5 size-4 shrink-0 text-ik-jade-ink"
					aria-hidden="true"
				/>
				{{ benefit }}
			</li>
		</ul>
	</section>
</template>
