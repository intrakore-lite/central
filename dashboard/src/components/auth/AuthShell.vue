<script setup lang="ts">
import AuthShowcase from '@/components/auth/AuthShowcase.vue'
import { brand } from '@/lib/brand'

interface AuthShellProps {
	step?: number
	steps?: number
	showProgress?: boolean
}

withDefaults(defineProps<AuthShellProps>(), {
	step: 1,
	steps: 4,
	showProgress: false,
})
</script>

<template>
	<main class="flex min-h-screen bg-surface-gray-1">
		<!-- Inputs take the brand focus ring of the INTRAKORE sign-in. -->
		<section
			class="flex min-h-screen w-full flex-col md:w-1/2 [&_input:focus]:border-blueprint-300 [&_input:focus]:shadow-[0_0_0_1px_theme(colors.blueprint.300)]"
		>
			<div
				class="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center px-6 py-12"
			>
				<img
					v-if="brand.wordmark"
					:src="brand.wordmark"
					:alt="brand.name"
					class="mb-10 h-8 w-fit dark:brightness-0 dark:invert"
				/>
				<div v-else class="mb-10 flex items-center gap-2">
					<img
						:src="brand.logo"
						alt=""
						class="size-8 rounded-4 object-contain"
					/>
					<span class="text-lg-semibold text-ink-gray-9">{{ brand.name }}</span>
				</div>

				<div
					v-if="showProgress"
					class="vt-auth-progress mb-10 flex gap-2"
					aria-label="Signup progress"
				>
					<span
						v-for="index in steps"
						:key="index"
						class="h-1 flex-1 rounded-4"
						:class="index <= step ? 'bg-blueprint-700' : 'bg-surface-gray-3'"
					/>
				</div>

				<div class="vt-auth-step">
					<slot />
				</div>
			</div>
		</section>

		<AuthShowcase />
	</main>
</template>
