<script setup lang="ts">
import SetupShell from '@/components/onboarding/setup/SetupShell.vue'
import { features } from '@/lib/features'
</script>

<template>
	<!-- Step 3 (OPS-219) builds team invitations here. Until then the page says what happens next. -->
	<SetupShell :step="3">
		<div class="mx-auto w-full max-w-xl px-4 py-16 sm:px-6">
			<section class="rounded-ik-lg bg-white p-8 shadow-ik-2">
				<p class="mb-2 text-ik-kicker uppercase text-ik-primary">
					Step 3 of 4: Team
				</p>
				<h1 class="text-ik-headline-mobile text-ik-ink md:text-ik-headline">
					Your {{ features.managed ? 'site' : 'server' }} is being created
				</h1>
				<p class="mt-2 text-ik-body text-ik-slate">
					Your card is saved and nothing is charged today. We are building your
					workspace now. You can invite your team as soon as it is ready.
				</p>
				<RouterLink
					to="/servers"
					class="mt-8 flex h-12 w-full items-center justify-center gap-2 rounded-ik-md bg-ik-primary text-ik-label-lg font-bold text-white shadow-ik-button transition-colors hover:bg-ik-primary-hover focus-visible:shadow-ik-3 focus-visible:outline-none"
				>
					Go to my {{ features.managed ? 'sites' : 'servers' }}
					<span class="lucide-arrow-right size-5" aria-hidden="true" />
				</RouterLink>
			</section>
		</div>
	</SetupShell>
</template>
