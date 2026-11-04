<script setup lang="ts">
import { LoadingIndicator } from 'frappe-ui'
import { computed, toRef, useTemplateRef, watch } from 'vue'
import { useCardFrame } from '@/composables/useCardFrame'

interface PaymentCardFrameProps {
	team: string
	/** False until the billing details the card setup needs are saved. */
	active: boolean
	/** Saving the billing details before the form opens. */
	opening?: boolean
}

const props = defineProps<PaymentCardFrameProps>()
const emit = defineEmits<{ open: []; saved: [] }>()
const stripeElement = useTemplateRef<HTMLElement>('stripe')
const frame = useCardFrame(toRef(props, 'team'))

watch(
	() => props.active,
	(active) => {
		if (active && frame.mode.value === 'idle')
			frame.start(() => stripeElement.value)
	},
	{ immediate: true },
)
watch(frame.isSavedInFrame, (saved) => saved && emit('saved'))

// Checkout Flow's own button would read "Pay" for a 0 AED check, so the slot draws this one.
const saveCardLabel = computed(() => {
	if (frame.isCheckoutCardSaved.value) return 'Card saved'
	return frame.isSavingCheckoutCard.value ? 'Saving card…' : 'Save card'
})

function retry() {
	frame.start(() => stripeElement.value)
}

defineExpose({ confirm: frame.confirm, isReady: frame.isReady })
</script>

<template>
	<div>
		<p class="mb-1.5 block text-ik-label font-semibold text-ik-text">
			Card Details
		</p>

		<div
			v-if="frame.mode.value === 'idle'"
			class="flex flex-col items-start gap-3 rounded-ik-md border border-dashed border-ik-control bg-ik-canvas-soft p-4 sm:flex-row sm:items-center sm:justify-between"
		>
			<p class="flex items-center gap-2 text-ik-body-sm text-ik-muted">
				<span
					class="lucide-lock size-4 shrink-0 text-ik-primary"
					aria-hidden="true"
				/>
				Your card is entered on the payment provider's secure form.
			</p>
			<button
				type="button"
				class="flex h-11 shrink-0 items-center gap-2 rounded-ik-md bg-white px-4 text-ik-label text-ik-ink shadow-ik-line transition-colors hover:bg-ik-canvas-soft focus-visible:shadow-ik-focus focus-visible:outline-none disabled:opacity-60"
				:disabled="opening"
				@click="emit('open')"
			>
				<LoadingIndicator v-if="opening" class="size-4" />
				Open secure card form
			</button>
		</div>

		<div
			v-else-if="frame.mode.value === 'loading'"
			class="flex h-12 items-center gap-2 rounded-ik-md bg-ik-canvas-soft px-4 text-ik-body-sm text-ik-muted"
			aria-busy="true"
		>
			<LoadingIndicator class="size-4" />
			Opening the secure card form…
		</div>

		<template
			v-else-if="
				frame.mode.value === 'stripe' || frame.mode.value === 'checkout'
			"
		>
			<div
				ref="stripe"
				:class="
					frame.mode.value === 'stripe'
						? 'flex h-12 items-center rounded-ik-md bg-white px-4 shadow-ik-control'
						: 'min-h-[220px]'
				"
			/>
			<button
				v-if="frame.mode.value === 'checkout'"
				type="button"
				class="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-ik-md bg-white px-4 text-ik-label font-semibold text-ik-ink shadow-ik-line transition-colors hover:bg-ik-canvas-soft focus-visible:shadow-ik-focus focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
				:disabled="
					frame.isSavingCheckoutCard.value || frame.isCheckoutCardSaved.value
				"
				:aria-busy="frame.isSavingCheckoutCard.value || undefined"
				@click="frame.saveCheckoutCard"
			>
				<LoadingIndicator
					v-if="frame.isSavingCheckoutCard.value"
					class="size-4"
				/>
				<span
					v-else
					:class="
						frame.isCheckoutCardSaved.value
							? 'lucide-circle-check text-ik-jade-ink'
							: 'lucide-lock text-ik-primary'
					"
					class="size-4 shrink-0"
					aria-hidden="true"
				/>
				{{ saveCardLabel }}
			</button>
			<p
				v-if="frame.mode.value === 'checkout'"
				class="mt-1.5 text-ik-body-sm text-ik-muted"
			>
				Nothing is charged. Your bank may ask you to confirm the card.
			</p>
			<p
				v-if="frame.stripeError.value"
				class="mt-1.5 text-ik-body-sm text-ik-error"
				role="alert"
			>
				{{ frame.stripeError.value }}
			</p>
		</template>

		<iframe
			v-else-if="frame.mode.value === 'iframe'"
			:src="frame.handles.value?.iframe_url"
			title="Secure card form"
			class="h-[380px] w-full rounded-ik-md bg-white shadow-ik-control"
			allow="payment"
			sandbox="allow-forms allow-scripts allow-same-origin allow-top-navigation-by-user-activation allow-popups"
		/>

		<div
			v-else-if="frame.mode.value === 'redirect'"
			class="flex flex-col items-start gap-3 rounded-ik-md bg-ik-canvas-soft p-4"
		>
			<p class="text-ik-body-sm text-ik-muted">
				Your bank's page opens to save the card. You come back here when it is
				saved.
			</p>
			<button
				type="button"
				class="h-11 rounded-ik-md bg-white px-4 text-ik-label text-ik-ink shadow-ik-line hover:bg-ik-canvas-soft focus-visible:shadow-ik-focus focus-visible:outline-none"
				@click="frame.leaveForHostedPage"
			>
				Continue to the secure card page
			</button>
		</div>

		<p
			v-else-if="frame.mode.value === 'returned'"
			class="flex items-center gap-2 rounded-ik-md bg-ik-jade-soft px-4 py-3 text-ik-body-sm text-ik-jade-ink"
		>
			<span class="lucide-circle-check size-4" aria-hidden="true" />
			Card entered. Confirm it below.
		</p>

		<p
			v-else-if="frame.mode.value === 'unavailable'"
			class="rounded-ik-md bg-ik-error-soft px-4 py-3 text-ik-body-sm text-ik-error"
			role="alert"
		>
			Card payments are not available for this team yet. Contact support to
			finish your setup.
		</p>

		<div
			v-else
			class="flex flex-col items-start gap-2 rounded-ik-md bg-ik-error-soft px-4 py-3"
			role="alert"
		>
			<p class="text-ik-body-sm text-ik-error">{{ frame.error.value }}</p>
			<button
				type="button"
				class="text-ik-label text-ik-primary hover:underline"
				@click="retry"
			>
				Try again
			</button>
		</div>
	</div>
</template>
