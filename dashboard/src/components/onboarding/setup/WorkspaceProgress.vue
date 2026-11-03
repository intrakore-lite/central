<script setup lang="ts">
import { computed } from 'vue'
import type { SiteSetupState, SiteStage } from '@/types/onboarding'

interface WorkspaceProgressProps {
	state: SiteSetupState | null
	/** Shown when the state could not be read. */
	error?: string
	retrying?: boolean
}

const props = defineProps<WorkspaceProgressProps>()
defineEmits<{ retry: [] }>()

const STAGES: { stage: SiteStage; label: string }[] = [
	{ stage: 'building', label: 'Creating your server' },
	{ stage: 'starting', label: 'Starting your workspace' },
	{ stage: 'setting_up', label: 'Setting up your company' },
	{ stage: 'ready', label: 'Ready to invite' },
]
const ORDER: SiteStage[] = [
	'waiting',
	'building',
	'starting',
	'setting_up',
	'ready',
]

const stage = computed<SiteStage>(() => props.state?.stage ?? 'building')
const position = computed(() => ORDER.indexOf(stage.value))
const progress = computed(() => props.state?.progress ?? 10)
const isFailed = computed(() => stage.value === 'failed')

function status(entry: SiteStage): 'done' | 'current' | 'next' {
	const index = ORDER.indexOf(entry)
	if (stage.value === 'ready' || index < position.value) return 'done'
	return index === position.value ? 'current' : 'next'
}
</script>

<template>
	<section
		class="rounded-ik-lg p-5"
		:class="isFailed ? 'bg-ik-error-soft' : 'bg-ik-primary-soft/50'"
		aria-live="polite"
		:aria-busy="!isFailed || undefined"
	>
		<div class="flex items-start gap-3">
			<span
				class="flex size-10 shrink-0 items-center justify-center rounded-ik-md"
				:class="isFailed ? 'bg-white text-ik-error' : 'bg-white text-ik-primary'"
				aria-hidden="true"
			>
				<span
					class="size-5"
					:class="
						isFailed ? 'lucide-triangle-alert' : 'lucide-loader-circle animate-spin'
					"
				/>
			</span>
			<div class="min-w-0 flex-1">
				<p class="text-ik-label text-ik-text">
					{{ isFailed
							? 'Your workspace needs attention'
							: stage === 'waiting'
								? 'Your workspace starts once your card is saved'
								: 'We are building your workspace' }}
				</p>
				<p class="mt-0.5 text-ik-body-sm text-ik-slate">
					{{ isFailed
							? state?.message || 'Something went wrong while we set it up.'
							: 'This takes a few minutes. You can fill in your team now and send the invitations when it is ready.' }}
				</p>
				<div
					v-if="!isFailed"
					class="mt-3 h-2 overflow-hidden rounded-full bg-white"
					role="progressbar"
					aria-label="Workspace setup"
					aria-valuemin="0"
					aria-valuemax="100"
					:aria-valuenow="progress"
				>
					<div
						class="h-full rounded-full bg-ik-primary transition-[width] duration-700"
						:style="{ width: `${Math.max(progress, 8)}%` }"
					/>
				</div>
				<ol
					v-if="!isFailed"
					class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-ik-label-sm sm:grid-cols-4"
				>
					<li
						v-for="entry in STAGES"
						:key="entry.stage"
						class="flex items-center gap-1.5"
						:class="
							status(entry.stage) === 'next' ? 'text-ik-outline' : 'text-ik-text'
						"
					>
						<span
							class="size-3.5 shrink-0"
							:class="{
								'lucide-circle-check text-ik-jade-ink':
									status(entry.stage) === 'done',
								'lucide-circle-dot text-ik-primary':
									status(entry.stage) === 'current',
								'lucide-circle text-ik-outline': status(entry.stage) === 'next',
							}"
							aria-hidden="true"
						/>
						{{ entry.label }}
					</li>
				</ol>
				<p v-if="error" class="mt-2 text-ik-body-sm text-ik-error" role="alert">
					{{ error }}
				</p>
				<button
					v-if="isFailed && state?.site"
					type="button"
					class="mt-3 h-10 rounded-ik-md bg-white px-4 text-ik-label text-ik-ink shadow-ik-line hover:bg-ik-canvas-soft focus-visible:shadow-ik-focus focus-visible:outline-none disabled:opacity-60"
					:disabled="retrying"
					@click="$emit('retry')"
				>
					Try the setup again
				</button>
			</div>
		</div>
	</section>
</template>
