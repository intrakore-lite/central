<script setup lang="ts">
import { signInShowcase } from '@/lib/brand'
import type { TrustContent } from '@/types/onboarding'

interface ProfileShowcaseProps {
	productTitle: string | null
	/** Null until the onboarding read answers. */
	trust: TrustContent | null
}

defineProps<ProfileShowcaseProps>()
</script>

<template>
	<aside
		class="relative flex w-full flex-col justify-between overflow-hidden bg-ik-canvas px-6 py-12 sm:px-12 lg:w-1/2 lg:px-16"
	>
		<div class="z-10 mx-auto mb-8 w-full max-w-xl lg:mx-0">
			<p class="mb-3 text-ik-kicker uppercase text-ik-primary">
				{{ signInShowcase.eyebrow }}
			</p>
			<h2 class="mb-4 text-ik-display-mobile text-ik-ink md:text-ik-display">
				{{ signInShowcase.headline }}
			</h2>
			<p class="text-ik-body-lg text-ik-slate">{{ signInShowcase.summary }}</p>
		</div>

		<div class="relative z-10 mx-auto w-full max-w-2xl lg:mx-0">
			<div
				class="pointer-events-none absolute -left-6 -top-6 grid size-24 grid-cols-6 gap-2 opacity-20"
				aria-hidden="true"
			>
				<span
					v-for="dot in 12"
					:key="dot"
					class="size-1.5 rounded-full bg-ik-primary-deep"
				/>
			</div>

			<div class="w-full overflow-hidden rounded-ik-xl bg-white shadow-ik-hero">
				<div class="flex items-center justify-between bg-ik-panel/50 px-5 py-4">
					<div class="flex items-center gap-3">
						<div class="flex items-center gap-1.5" aria-hidden="true">
							<span class="size-3 rounded-full bg-ik-error" />
							<span class="size-3 rounded-full bg-ik-amber" />
							<span class="size-3 rounded-full bg-ik-jade-bright" />
						</div>
						<span class="pl-2 text-ik-kicker uppercase text-ik-primary">
							Intrakore Hub
						</span>
					</div>
					<span
						v-if="productTitle"
						class="rounded-full bg-ik-chip px-2 py-0.5 text-ik-label-sm text-ik-muted"
					>
						{{ productTitle }}
					</span>
				</div>
				<img
					:src="signInShowcase.image"
					alt="The Intrakore dashboard: order book, monthly burn, runway and pipeline"
					class="block w-full object-contain p-3"
				/>
			</div>

			<div
				v-if="trust"
				class="absolute -bottom-8 -right-6 z-20 hidden items-center gap-3 rounded-ik-lg bg-white p-3 pr-5 shadow-ik-hero sm:flex"
			>
				<span
					class="flex size-12 items-center justify-center rounded-ik-md bg-ik-jade-soft text-ik-jade-ink"
					aria-hidden="true"
				>
					<span class="lucide-trending-up size-6" />
				</span>
				<div class="flex flex-col">
					<span class="text-ik-label font-bold text-ik-text">
						{{ trust.proof.title }}
					</span>
					<span class="text-ik-body-sm text-ik-muted">
						{{ trust.proof.text }}
					</span>
				</div>
			</div>
		</div>

		<p
			v-if="trust"
			class="z-10 mx-auto flex w-full max-w-xl items-center gap-3 pt-14 text-ik-label font-semibold text-ik-text lg:mx-0"
		>
			<span
				class="lucide-badge-check size-5 shrink-0 text-ik-primary"
				aria-hidden="true"
			/>
			{{ trust.profile_trust_line }}
		</p>
	</aside>
</template>
