<script setup lang="ts">
import { brand } from '@/lib/brand'
import type { TrustLine } from '@/types/onboarding'

interface SetupHelpRibbonProps {
	help: TrustLine
}

defineProps<SetupHelpRibbonProps>()

const supportUrl = window.help_links?.support_ticket_url ?? null
</script>

<template>
	<div
		class="flex items-center justify-between gap-3 rounded-ik-md bg-ik-chip p-4 text-ik-text"
	>
		<div class="flex items-center gap-3">
			<span
				class="lucide-headset size-6 shrink-0 text-ik-primary"
				aria-hidden="true"
			/>
			<div>
				<p class="text-ik-label font-bold">{{ help.title }}</p>
				<p class="text-ik-body-sm text-ik-slate">{{ help.text }}</p>
			</div>
		</div>
		<a
			:href="supportUrl ?? brand.docsUrl"
			target="_blank"
			rel="noopener"
			class="whitespace-nowrap pl-2 text-ik-label-sm font-bold text-ik-primary hover:underline"
		>
			{{ supportUrl ? 'Contact us' : 'Read the docs' }}
		</a>
	</div>
</template>
