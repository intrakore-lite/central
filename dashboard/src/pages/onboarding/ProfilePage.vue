<script setup lang="ts">
import { Button } from 'frappe-ui'
import AuthShell from '@/components/auth/AuthShell.vue'
import { brand } from '@/lib/brand'
</script>

<!-- A placeholder for the first step of the invited onboarding (OPS-216), which replaces it. -->
<template>
	<AuthShell>
		<h1 class="text-2xl font-semibold text-ink-gray-9">
			Your account is active
		</h1>
		<p class="mt-1 text-p-base text-ink-gray-5">
			Next you set up your organisation. Until that step is ready, continue to
			{{ brand.name }}.
		</p>
		<Button
			class="mt-8 w-full"
			size="md"
			variant="solid"
			route="/servers"
			:label="`Open ${brand.name}`"
		/>
	</AuthShell>
</template>
