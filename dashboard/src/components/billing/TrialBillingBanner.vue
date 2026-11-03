<script setup lang="ts">
import { Alert } from 'frappe-ui'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useBillingSetup } from '@/composables/useBillingSetup'
import { formatDate, money, plural } from '@/lib/format'

interface Props {
	/** Off inside a dialog, where leaving the page would lose the dialog. */
	linkToUpgrade?: boolean
}

const props = withDefaults(defineProps<Props>(), { linkToUpgrade: true })

const router = useRouter()
const { profile } = useBillingSetup()

// A card on file pays for an Active trial from its end date. An Ended trial is kept only
// from its server's Upgrade dialog.
const trial = computed(() => profile.value?.open_trial ?? null)
const isEnded = computed(() => trial.value?.state === 'Ended')

const siteName = computed(() =>
	trial.value?.product ? `Your ${trial.value.product_title} site` : 'Your site',
)

const planText = computed(() => {
	const seats = trial.value?.seats
	if (seats)
		return `${plural(seats.seats, 'seat')} at ${money(seats.monthly_rate, seats.currency, { trimTrailingZeros: true })} a month`
	const plan = trial.value?.plan
	if (!plan) return 'its paid plan'
	const price =
		plan.currency && plan.monthly_rate
			? ` at ${money(plan.monthly_rate, plan.currency, { trimTrailingZeros: true })} a month`
			: ''
	return `the ${plan.title} plan${price}`
})

const title = computed(() =>
	isEnded.value
		? 'Your free trial has ended'
		: 'Your account is on a free trial',
)

const description = computed(() =>
	isEnded.value
		? `${siteName.value} is stopped and will be deleted. To keep it, add a payment method and choose Keep this site.`
		: `${siteName.value} stays free until ${formatDate(trial.value?.ends_on) || 'the trial ends'}. Then it moves to ${planText.value}, and billing starts with the card on file.`,
)

const action = computed(() => {
	const server = trial.value?.server
	if (!props.linkToUpgrade || !server) return undefined

	return {
		label: isEnded.value ? 'Keep this site' : 'Upgrade site',
		onClick: () =>
			router.push({ path: `/servers/${server}`, query: { action: 'resize' } }),
	}
})
</script>

<template>
	<Alert
		v-if="trial"
		:theme="isEnded ? 'red' : 'blue'"
		:title="title"
		:description="description"
		:primary-action="action"
	/>
</template>
