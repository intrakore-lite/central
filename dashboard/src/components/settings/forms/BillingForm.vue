<script setup lang="ts">
import { Alert, Button, LoadingText } from 'frappe-ui'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import SettingsSection from '@/components/common/SettingsSection.vue'
import { useCapabilities } from '@/composables/useCapabilities'
import { useSeats } from '@/composables/useSeats'
import { settingsOpen } from '@/composables/useSettings'
import { formatDate, money, plural } from '@/lib/format'

// The seats of a site billed per seat: change the count with a price preview, or cancel.
// The site's user limit and its size follow the seat count, so neither is shown here.
const MAX_SEATS = 1000
const PREVIEW_DELAY_MS = 300

const router = useRouter()
const { canManageBilling } = useCapabilities()
const {
	summary,
	loading,
	loadError,
	preview,
	previewLoading,
	saving,
	error,
	previewSeats,
	changeSeats,
	setCancelled,
	clearError,
} = useSeats()

const count = ref(0)
watch(
	() => summary.value?.seats,
	(seats) => {
		count.value = seats ?? 0
	},
	{ immediate: true },
)

const currency = computed(() => summary.value?.currency ?? 'USD')
const price = (amount: number | null | undefined) =>
	money(amount ?? 0, currency.value, { trimTrailingZeros: true })

const isChanged = computed(
	() => !!summary.value?.seats && count.value !== summary.value.seats,
)

let timer: number | undefined
watch(count, (seats) => {
	clearError()
	window.clearTimeout(timer)
	if (!isChanged.value) return
	timer = window.setTimeout(() => previewSeats(seats), PREVIEW_DELAY_MS)
})
onScopeDispose(() => window.clearTimeout(timer))

const priceLine = computed(() => {
	const current = summary.value
	if (!current?.is_seat_billed) return ''
	return `${price(current.seat_price)} per seat a month. The plan bills at least ${plural(current.included_seats ?? 0, 'seat')}.`
})

const storageLine = computed(() => {
	const current = summary.value
	if (!current?.storage_price_per_gb) return ''
	return `Includes ${current.included_storage_gb ?? 0} GB of storage. Extra storage is ${price(current.storage_price_per_gb)} per GB a month.`
})

const previewLine = computed(() => {
	const next = preview.value
	if (!isChanged.value || !next?.is_seat_billed || next.seats !== count.value)
		return ''
	const monthly = `${price(next.monthly_rate)} a month for ${plural(next.seats ?? 0, 'seat')}`
	if (next.is_on_trial)
		return `${monthly} from ${formatDate(next.billing_starts_on)}, plus tax. Nothing is charged during the free trial.`
	const change = next.prorated_amount ?? 0
	const direction = change < 0 ? 'goes down by' : 'goes up by'
	return `${monthly} from today. This month's bill ${direction} ${price(Math.abs(change))}, plus tax.`
})

function step(by: number): void {
	count.value = Math.min(MAX_SEATS, Math.max(1, count.value + by))
}

async function onSave(): Promise<void> {
	if (isChanged.value) await changeSeats(count.value)
}

const cancelTarget = ref<true | null>(null)
const cancelMessage = computed(() =>
	summary.value?.is_on_trial
		? `Your free trial runs until ${formatDate(summary.value.billing_starts_on)}. Your card is not charged, and your site stops on that day and is deleted later.`
		: 'You pay for the rest of this month. Your site stops at the end of the month and is deleted later.',
)

async function onCancel(): Promise<void> {
	if (await setCancelled(true)) cancelTarget.value = null
}

function openBilling(): void {
	settingsOpen.value = false
	router.push('/billing')
}
</script>

<template>
	<div class="mt-6">
		<LoadingText v-if="loading" :lines="3" />
		<Alert
			v-else-if="loadError"
			theme="red"
			title="Couldn't load your seats"
			:description="loadError"
		/>
		<EmptyState
			v-else-if="!summary?.is_seat_billed"
			icon="lucide-users"
			title="This team has no seats"
			description="Your sites are billed by their plan. See what you pay on the Billing page."
		>
			<template #action>
				<Button label="Open Billing" @click="openBilling" />
			</template>
		</EmptyState>

		<template v-else>
			<SettingsSection title="Seats" :description="priceLine">
				<div class="space-y-4">
					<Alert v-if="error && !cancelTarget" theme="red" :title="error" />
					<div class="flex flex-wrap items-center gap-3">
						<div
							class="flex items-center gap-1"
							role="group"
							aria-label="Seats"
						>
							<Button
								icon="lucide-minus"
								aria-label="Remove a seat"
								:disabled="!canManageBilling || saving || count <= 1"
								@click="step(-1)"
							/>
							<span
								class="min-w-12 text-center text-lg-semibold tabular-nums text-ink-gray-9"
								aria-live="polite"
							>
								{{ count }}
							</span>
							<Button
								icon="lucide-plus"
								aria-label="Add a seat"
								:disabled="!canManageBilling || saving || count >= MAX_SEATS"
								@click="step(1)"
							/>
						</div>
						<span class="text-p-base text-ink-gray-7">
							{{ price(summary.current_monthly_rate) }}
							a month now
						</span>
						<Button
							v-if="canManageBilling && isChanged"
							class="ml-auto"
							variant="solid"
							:label="`Change to ${plural(count, 'seat')}`"
							:loading="saving"
							:disabled="previewLoading"
							@click="onSave"
						/>
					</div>
					<p v-if="previewLine" class="text-p-sm text-ink-gray-7">
						{{ previewLine }}
					</p>
					<p v-if="storageLine" class="text-p-sm text-ink-gray-6">
						{{ storageLine }}
					</p>
					<p v-if="!canManageBilling" class="text-p-sm text-ink-gray-5">
						Changing seats requires the Owner, Admin or Billing role.
					</p>
				</div>
			</SettingsSection>

			<SettingsSection
				class="border-t border-outline-gray-1"
				title="Subscription"
				:description="
					summary.is_on_trial
						? `Your free trial ends on ${formatDate(summary.billing_starts_on)}. Billing starts then, with the card on file.`
						: 'Billed monthly for your seats.'
				"
			>
				<Alert
					v-if="summary.subscription_ends_on"
					theme="amber"
					:title="`Your subscription ends on ${formatDate(summary.subscription_ends_on)}`"
					description="Your site stops after this day and is deleted later. Keep the subscription to stay on your plan."
					:primary-action="
						canManageBilling
							? { label: 'Keep subscription', onClick: () => setCancelled(false) }
							: undefined
					"
				/>
				<div v-else-if="canManageBilling">
					<Button
						theme="red"
						label="Cancel subscription"
						@click="cancelTarget = true"
					/>
				</div>
			</SettingsSection>
		</template>

		<ConfirmDialog
			v-model:target="cancelTarget"
			title="Cancel subscription?"
			:message="cancelMessage"
			confirm-label="Cancel subscription"
			theme="red"
			:loading="saving"
			:error="error"
			@confirm="onCancel"
		/>
	</div>
</template>
