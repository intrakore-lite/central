<script setup lang="ts">
import '@/assets/fonts/plus-jakarta-sans/plus-jakarta-sans.css'
import { computed } from 'vue'
import SetupStepper from '@/components/onboarding/setup/SetupStepper.vue'
import { useMyProfile } from '@/composables/useMyProfile'
import { useSession } from '@/composables/useSession'
import { brand } from '@/lib/brand'

interface SetupShellProps {
	/** The current step, from 1. */
	step: number
}

defineProps<SetupShellProps>()

const { profile } = useMyProfile()
const { activeTeamLabel } = useSession()
const supportUrl = window.help_links?.support_ticket_url ?? null
const year = new Date().getFullYear()

const initials = computed(() =>
	(profile.value?.full_name || window.user || '')
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((word) => word[0].toUpperCase())
		.join(''),
)
</script>

<template>
	<!-- The onboarding pages wear the Intrakore Construction Cloud design, not Espresso. -->
	<div
		class="flex min-h-screen flex-col bg-ik-canvas font-ik text-ik-body tracking-normal text-ik-text antialiased"
		data-theme="light"
	>
		<header
			class="sticky top-0 z-50 w-full bg-white/90 shadow-ik-header backdrop-blur-xl"
		>
			<div
				class="flex h-16 w-full items-center justify-between gap-6 px-4 sm:px-8"
			>
				<div class="flex min-w-0 items-center gap-3 lg:min-w-[220px]">
					<img
						v-if="brand.wordmark"
						:src="brand.wordmark"
						:alt="brand.name"
						class="h-6 w-auto"
					/>
					<img v-else :src="brand.logo" alt="" class="size-8 object-contain" />
					<div class="flex flex-col">
						<span
							v-if="!brand.wordmark"
							class="text-ik-label-lg font-bold text-ik-primary"
						>
							{{ brand.name }}
						</span>
						<span
							class="hidden text-ik-kicker uppercase text-ik-muted sm:block"
						>
							Construction Cloud
						</span>
					</div>
				</div>

				<SetupStepper
					:step="step"
					class="hidden flex-1 justify-center lg:flex"
				/>

				<div class="flex items-center justify-end gap-4 lg:min-w-[220px]">
					<a
						:href="brand.docsUrl"
						target="_blank"
						rel="noopener"
						class="flex items-center gap-1 rounded-ik-sm px-3 py-1 text-ik-label-sm text-ik-muted transition-colors hover:bg-ik-chip hover:text-ik-text focus-visible:shadow-ik-focus focus-visible:outline-none"
					>
						<span class="lucide-circle-help size-[18px]" aria-hidden="true" />
						<span class="hidden xl:inline">Support &amp; Docs</span>
						<span class="sr-only xl:hidden">Support and docs</span>
					</a>
					<div class="h-6 w-px bg-ik-line" aria-hidden="true" />
					<div class="flex items-center gap-2">
						<img
							v-if="profile?.user_image"
							:src="profile.user_image"
							alt=""
							class="size-8 rounded-full object-cover ring-2 ring-ik-primary-soft"
						/>
						<span
							v-else
							class="flex size-8 items-center justify-center rounded-full bg-ik-primary-soft text-ik-label-sm text-ik-primary ring-2 ring-ik-primary-soft"
							aria-hidden="true"
						>
							{{ initials }}
						</span>
						<div class="hidden max-w-[160px] flex-col text-left xl:flex">
							<span class="truncate text-ik-label-sm text-ik-text">
								{{ profile?.full_name || 'Account' }}
							</span>
							<span class="truncate text-ik-kicker text-ik-muted">
								{{ activeTeamLabel }}
							</span>
						</div>
					</div>
				</div>
			</div>
		</header>

		<main class="w-full flex-1">
			<slot />
		</main>

		<footer class="w-full bg-white py-6 shadow-ik-header">
			<div
				class="flex w-full flex-col items-center justify-between gap-4 px-4 text-center text-ik-label-sm text-ik-muted sm:px-8 md:flex-row md:text-left"
			>
				<span>© {{ year }} {{ brand.name }}. All rights reserved.</span>
				<nav aria-label="Help" class="flex items-center gap-6">
					<a
						v-if="brand.policiesUrl"
						:href="brand.policiesUrl"
						target="_blank"
						rel="noopener"
						class="transition-colors hover:text-ik-primary"
					>
						Terms &amp; policies
					</a>
					<a
						:href="brand.docsUrl"
						target="_blank"
						rel="noopener"
						class="transition-colors hover:text-ik-primary"
					>
						Docs
					</a>
					<a
						v-if="supportUrl"
						:href="supportUrl"
						target="_blank"
						rel="noopener"
						class="transition-colors hover:text-ik-primary"
					>
						Support desk
					</a>
				</nav>
			</div>
		</footer>
	</div>
</template>
