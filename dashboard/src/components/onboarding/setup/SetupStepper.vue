<script setup lang="ts">
import { SETUP_STEPS } from '@/components/onboarding/setup/steps'

interface SetupStepperProps {
	/** The current step, from 1. */
	step: number
}

defineProps<SetupStepperProps>()
</script>

<template>
	<nav aria-label="Setup progress">
		<ol class="flex items-center gap-6">
			<template v-for="(item, index) in SETUP_STEPS" :key="item.label">
				<li
					v-if="index > 0"
					class="text-ik-label-sm text-ik-outline/60"
					aria-hidden="true"
				>
					→
				</li>
				<li
					class="flex items-center gap-1 text-ik-label"
					:class="index + 1 === step ? 'text-ik-primary' : 'text-ik-muted'"
					:aria-current="index + 1 === step ? 'step' : undefined"
				>
					<span
						class="flex size-6 items-center justify-center rounded-full text-ik-label-sm"
						:class="
							index + 1 <= step
								? 'bg-ik-primary-soft text-ik-primary'
								: 'bg-ik-chip-hover text-ik-muted'
						"
					>
						<span
							v-if="index + 1 < step"
							class="lucide-check size-3.5"
							aria-label="Done"
						/>
						<template v-else>{{ index + 1 }}</template>
					</span>
					<span>{{ item.label }}</span>
				</li>
			</template>
		</ol>
	</nav>
</template>
